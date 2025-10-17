class MetricQueries:
    @staticmethod
    def get_spend_metrics(time_window: str) -> str:
        return """
        WITH spend_data AS (
            SELECT
                s.model,
                SUM(s.spend) as total_spend,
                SUM(s.total_tokens) as total_tokens,
                SUM(s.prompt_tokens) as prompt_tokens,
                SUM(s.completion_tokens) as completion_tokens,
                COUNT(*) as request_count,
                COUNT(CASE WHEN s.cache_hit = 'true' THEN 1 END) as cache_hits,
                COUNT(CASE WHEN s.cache_hit = 'false' THEN 1 END) as cache_misses,
                u.user_id,
                u.user_alias,
                t.team_id,
                t.team_alias,
                o.organization_id,
                o.organization_alias
            FROM "LiteLLM_SpendLogs" s
            LEFT JOIN "LiteLLM_UserTable" u ON s."user" = u.user_id
            LEFT JOIN "LiteLLM_TeamTable" t ON s.team_id = t.team_id
            LEFT JOIN "LiteLLM_OrganizationTable" o ON t.organization_id = o.organization_id
            WHERE s."startTime" >= NOW() - INTERVAL %(time_window)s
            GROUP BY s.model, u.user_id, u.user_alias, t.team_id, t.team_alias,
                     o.organization_id, o.organization_alias
        )
        SELECT * FROM spend_data
        """

    @staticmethod
    def get_rate_limits() -> str:
        return """
        -- Get user rate limits and blocked status
        SELECT
            'user' as entity_type,
            u.user_id as entity_id,
            u.user_alias as entity_alias,
            u.tpm_limit,
            u.rpm_limit,
            u.max_parallel_requests,
            CASE
                WHEN e.blocked = true THEN true
                ELSE false
            END as is_blocked
        FROM "LiteLLM_UserTable" u
        LEFT JOIN "LiteLLM_EndUserTable" e ON u.user_id = e.user_id
        WHERE u.tpm_limit IS NOT NULL
           OR u.rpm_limit IS NOT NULL
           OR u.max_parallel_requests IS NOT NULL
           OR e.blocked = true

        UNION ALL

        -- Get team rate limits and blocked status
        SELECT
            'team' as entity_type,
            team_id as entity_id,
            team_alias as entity_alias,
            tpm_limit,
            rpm_limit,
            max_parallel_requests,
            blocked as is_blocked
        FROM "LiteLLM_TeamTable"
        WHERE tpm_limit IS NOT NULL
           OR rpm_limit IS NOT NULL
           OR max_parallel_requests IS NOT NULL
           OR blocked = true
        """

    @staticmethod
    def get_budget_metrics() -> str:
        return """
        WITH budget_data AS (
            -- User budgets from EndUserTable
            SELECT
                b.budget_id,
                b.max_budget,
                b.soft_budget,
                b.budget_reset_at,
                e.user_id as entity_id,
                'user' as entity_type,
                u.user_alias as entity_alias,
                u.spend as current_spend
            FROM "LiteLLM_BudgetTable" b
            JOIN "LiteLLM_EndUserTable" e ON e.budget_id = b.budget_id
            LEFT JOIN "LiteLLM_UserTable" u ON u.user_id = e.user_id

            UNION ALL

            -- Team budgets from TeamMembership
            SELECT
                b.budget_id,
                b.max_budget,
                b.soft_budget,
                b.budget_reset_at,
                tm.team_id as entity_id,
                'team' as entity_type,
                t.team_alias as entity_alias,
                t.spend as current_spend
            FROM "LiteLLM_BudgetTable" b
            JOIN "LiteLLM_TeamMembership" tm ON tm.budget_id = b.budget_id
            LEFT JOIN "LiteLLM_TeamTable" t ON t.team_id = tm.team_id

            UNION ALL

            -- Organization budgets from OrganizationMembership
            SELECT
                b.budget_id,
                b.max_budget,
                b.soft_budget,
                b.budget_reset_at,
                om.organization_id as entity_id,
                'organization' as entity_type,
                o.organization_alias as entity_alias,
                o.spend as current_spend
            FROM "LiteLLM_BudgetTable" b
            JOIN "LiteLLM_OrganizationMembership" om ON om.budget_id = b.budget_id
            LEFT JOIN "LiteLLM_OrganizationTable" o ON o.organization_id = om.organization_id
        )
        SELECT * FROM budget_data
        """

    @staticmethod
    def get_key_metrics() -> str:
        return """
        SELECT
            token,
            key_name,
            key_alias,
            expires,
            user_id,
            team_id,
            blocked,
            spend
        FROM "LiteLLM_VerificationToken"
        """

    @staticmethod
    def get_key_spend() -> str:
        return """
        SELECT
            v.key_name,
            v.key_alias,
            SUM(l.spend) AS total_spend
        FROM "LiteLLM_SpendLogs" l
        LEFT JOIN "LiteLLM_VerificationToken" v ON l.api_key = v.token
        WHERE l."startTime" >= NOW() - INTERVAL '30 days'
        GROUP BY v.key_name, v.key_alias
        ORDER BY total_spend DESC
        """

    @staticmethod
    def get_key_budget_metrics() -> str:
        return """
        SELECT
            v.key_name,
            v.key_alias,
            COALESCE(v.max_budget, b.max_budget) AS max_budget,
            COALESCE(v.budget_reset_at, b.budget_reset_at) AS budget_reset_at,
            (
                SELECT COALESCE(SUM(l.spend), 0)
                FROM "LiteLLM_SpendLogs" l
                WHERE l.api_key = v.token
                AND (
                    COALESCE(v.budget_reset_at, b.budget_reset_at) IS NULL
                    OR l."startTime" >= COALESCE(v.budget_reset_at, b.budget_reset_at)
                )
            ) AS current_spend
        FROM "LiteLLM_VerificationToken" v
        LEFT JOIN "LiteLLM_BudgetTable" b ON v.budget_id = b.budget_id
        WHERE v.max_budget IS NOT NULL OR b.max_budget IS NOT NULL
        """

    @staticmethod
    def get_current_rate_metrics() -> str:
        return """
        -- User-level current rates
        SELECT
            s.model,
            'user' as entity_type,
            u.user_id as entity_id,
            COALESCE(u.user_alias, 'none') as entity_alias,
            SUM(s.total_tokens) as total_tokens,
            COUNT(*) as request_count
        FROM "LiteLLM_SpendLogs" s
        LEFT JOIN "LiteLLM_UserTable" u ON s."user" = u.user_id
        WHERE s."startTime" >= NOW() - INTERVAL '1 minute'
          AND u.user_id IS NOT NULL
        GROUP BY s.model, u.user_id, u.user_alias

        UNION ALL

        -- Team-level current rates
        SELECT
            s.model,
            'team' as entity_type,
            t.team_id as entity_id,
            COALESCE(t.team_alias, 'none') as entity_alias,
            SUM(s.total_tokens) as total_tokens,
            COUNT(*) as request_count
        FROM "LiteLLM_SpendLogs" s
        LEFT JOIN "LiteLLM_TeamTable" t ON s.team_id = t.team_id
        WHERE s."startTime" >= NOW() - INTERVAL '1 minute'
          AND t.team_id IS NOT NULL
        GROUP BY s.model, t.team_id, t.team_alias

        UNION ALL

        -- Organization-level current rates
        SELECT
            s.model,
            'organization' as entity_type,
            o.organization_id as entity_id,
            COALESCE(o.organization_alias, 'none') as entity_alias,
            SUM(s.total_tokens) as total_tokens,
            COUNT(*) as request_count
        FROM "LiteLLM_SpendLogs" s
        LEFT JOIN "LiteLLM_TeamTable" t ON s.team_id = t.team_id
        LEFT JOIN "LiteLLM_OrganizationTable" o ON t.organization_id = o.organization_id
        WHERE s."startTime" >= NOW() - INTERVAL '1 minute'
          AND o.organization_id IS NOT NULL
        GROUP BY s.model, o.organization_id, o.organization_alias
        """
