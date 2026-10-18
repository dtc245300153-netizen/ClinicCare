
CREATE TABLE IF NOT EXISTS patients (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    date_of_birth DATE,
    phone VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS doctors (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    specialty VARCHAR(100) NOT NULL,
    phone VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS appointments (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    doctor_id INTEGER NOT NULL REFERENCES doctors(id),
    appointment_time TIMESTAMP NOT NULL,
    reason TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'scheduled'
);

INSERT INTO doctors (full_name, specialty, phone)
VALUES
    ('Nguyễn Văn An', 'Nội khoa', '0900000001'),
    ('Trần Thị Bình', 'Nhi khoa', '0900000002');
