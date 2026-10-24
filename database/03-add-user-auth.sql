\set ON_ERROR_STOP on
\getenv app_user APP_DB_USER

CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    role VARCHAR(20) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    doctor_id INTEGER REFERENCES public.doctors(id),
    CONSTRAINT users_role_check
        CHECK (role IN ('Admin', 'Doctor', 'Receptionist')),
    CONSTRAINT users_doctor_role_check
        CHECK ((role = 'Doctor' AND doctor_id IS NOT NULL) OR role <> 'Doctor')
);

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS doctor_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.users'::regclass
          AND conname = 'users_doctor_id_fkey'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_doctor_id_fkey
            FOREIGN KEY (doctor_id) REFERENCES public.doctors(id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.users'::regclass
          AND conname = 'users_doctor_id_key'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_doctor_id_key UNIQUE (doctor_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.users'::regclass
          AND conname = 'users_role_check'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_role_check
            CHECK (role IN ('Admin', 'Doctor', 'Receptionist'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.users'::regclass
          AND conname = 'users_doctor_role_check'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_doctor_role_check
            CHECK ((role = 'Doctor' AND doctor_id IS NOT NULL) OR role <> 'Doctor');
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_unique
    ON public.users (lower(username));

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.users TO :"app_user";
GRANT USAGE, SELECT ON SEQUENCE public.users_id_seq TO :"app_user";
