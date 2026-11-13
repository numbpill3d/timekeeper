-- Keep registration/login identity consistent for legacy and new accounts.

DO $$
BEGIN
    -- Never silently merge or pick a winner between existing accounts.
    IF EXISTS (
        SELECT lower(email)
        FROM users
        GROUP BY lower(email)
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'cannot canonicalize user emails: case-insensitive duplicates exist';
    END IF;

    UPDATE users
       SET email = lower(email)
     WHERE email <> lower(email);
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_idx
    ON users (lower(email));

INSERT INTO schema_migrations (version)
VALUES ('003_user_email_canonicalization')
ON CONFLICT (version) DO NOTHING;
