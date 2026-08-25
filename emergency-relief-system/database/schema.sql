CREATE DATABASE IF NOT EXISTS emergency_relief_db;

-- The Flask application owns the portable schema through SQLAlchemy db.create_all().
-- This file is intentionally limited to database creation so MySQL initialization
-- remains compatible with SQLite-based tests and local development.
USE emergency_relief_db;
