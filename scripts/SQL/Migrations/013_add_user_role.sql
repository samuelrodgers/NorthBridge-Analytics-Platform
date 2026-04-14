-- Migration 013: Add role column to auth.users
-- Existing users default to 'viewer'; promote admins manually after running.
ALTER TABLE auth.users
  ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'viewer';
