-- 1. Create the new schema (touches nothing existing)
CREATE SCHEMA IF NOT EXISTS auth;

-- 2. Create the users table inside it
CREATE TABLE auth.users (
    id                      SERIAL PRIMARY KEY,
    email                   VARCHAR(255) UNIQUE NOT NULL,
    name                    VARCHAR(255) NOT NULL,
    password_hash           TEXT NOT NULL,
    is_verified             BOOLEAN DEFAULT FALSE,
    reset_token             TEXT,
    reset_token_expires_at  TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);