import os
import re
import unittest
from datetime import datetime

from flask import g

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["FLASK_SECRET_KEY"] = "test-only-secret-key"

from app import Appointment, Doctor, Patient, User, app, db  # noqa: E402


class AuthRbacTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.client = app.test_client()

        doctor = Doctor(full_name="Bác sĩ Một", specialty="Nội khoa")
        other_doctor = Doctor(full_name="Bác sĩ Hai", specialty="Nhi khoa")
        patient = Patient(full_name="Bệnh nhân Một")
        other_patient = Patient(full_name="Bệnh nhân Hai")
        db.session.add_all([doctor, other_doctor, patient, other_patient])
        db.session.flush()
        self.appointment = Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            appointment_time=datetime(2030, 1, 2, 10, 0),
            reason="Khám định kỳ",
        )
        self.other_appointment = Appointment(
            patient_id=other_patient.id,
            doctor_id=other_doctor.id,
            appointment_time=datetime(2030, 1, 3, 11, 0),
            reason="Khám riêng",
        )
        self.doctor = doctor
        self.other_doctor = other_doctor
        self.patient = patient
        self.other_patient = other_patient
        self.admin = self.add_user("admin", "Admin")
        self.receptionist = self.add_user("frontdesk", "Receptionist")
        self.doctor_user = self.add_user(
            "doctor", "Doctor", doctor_id=doctor.id
        )
        db.session.add_all([self.appointment, self.other_appointment])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    @staticmethod
    def add_user(username, role, doctor_id=None, active=True):
        user = User(
            username=username,
            full_name=username.title(),
            role=role,
            doctor_id=doctor_id,
            is_active=active,
        )
        user.set_password("correct-horse-battery")
        db.session.add(user)
        db.session.flush()
        return user

    def csrf_token(self, path="/login"):
        g.pop("csrf_token", None)
        response = self.client.get(path)
        match = re.search(
            rb'name="csrf_token" value="([^"]+)"', response.data
        )
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def login(self, username, password="correct-horse-battery"):
        token = self.csrf_token()
        return self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "username": username,
                "password": password,
            },
        )

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get("/patients")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_admin_can_manage_accounts_and_cannot_disable_last_admin(self):
        self.login("admin")
        response = self.client.get("/admin/users")
        self.assertEqual(response.status_code, 200)
        token = self.csrf_token("/admin/users")
        response = self.client.post(
            f"/admin/users/{self.admin.id}/update",
            data={
                "csrf_token": token,
                "role": "Receptionist",
                "is_active": "false",
            },
        )
        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.admin)
        self.assertEqual(self.admin.role, "Admin")
        self.assertTrue(self.admin.is_active)

    def test_admin_can_create_a_hashed_user_account(self):
        self.login("admin")
        token = self.csrf_token("/admin/users")
        response = self.client.post(
            "/admin/users",
            data={
                "csrf_token": token,
                "username": "new-frontdesk",
                "full_name": "Nhân viên mới",
                "password": "new-secure-password",
                "role": "Receptionist",
                "doctor_id": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = User.query.filter_by(username="new-frontdesk").one()
        self.assertEqual(created.role, "Receptionist")
        self.assertNotEqual(created.password_hash, "new-secure-password")
        self.assertTrue(created.check_password("new-secure-password"))

    def test_disabling_user_revokes_the_existing_session(self):
        self.login("admin")
        admin_session = self.client
        receptionist_session = app.test_client()
        self.client = receptionist_session
        g.pop("_login_user", None)
        self.login("frontdesk")
        self.client = admin_session
        g.pop("_login_user", None)
        self.add_user("second-admin", "Admin")
        db.session.commit()
        token = self.csrf_token("/admin/users")
        response = self.client.post(
            f"/admin/users/{self.receptionist.id}/update",
            data={
                "csrf_token": token,
                "role": "Receptionist",
                "is_active": "false",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.client = receptionist_session
        g.pop("_login_user", None)
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_doctor_and_receptionist_cannot_manage_accounts_or_escalate(self):
        for username in ("doctor", "frontdesk"):
            self.client = app.test_client()
            g.pop("_login_user", None)
            self.login(username)
            self.assertEqual(self.client.get("/admin/users").status_code, 403)
            token = self.csrf_token("/appointments")
            response = self.client.post(
                "/admin/users",
                data={
                    "csrf_token": token,
                    "username": "self-admin",
                    "full_name": "Unauthorized",
                    "password": "correct-horse-battery",
                    "role": "Admin",
                },
            )
            self.assertEqual(response.status_code, 403)
            self.assertIsNone(User.query.filter_by(username="self-admin").first())
            response = self.client.post(
                f"/admin/users/{self.receptionist.id}/update",
                data={
                    "csrf_token": token,
                    "role": "Admin",
                    "is_active": "true",
                    "doctor_id": "",
                },
            )
            self.assertEqual(response.status_code, 403)
            db.session.refresh(self.receptionist)
            self.assertEqual(self.receptionist.role, "Receptionist")

    def test_locked_account_cannot_log_in(self):
        self.receptionist.is_active = False
        db.session.commit()
        response = self.login("frontdesk")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Tên đăng nhập hoặc mật khẩu không đúng".encode(), response.data)

    def test_doctor_only_sees_and_updates_assigned_appointments(self):
        self.login("doctor")
        self.assertEqual(self.client.get("/patients").status_code, 403)
        self.assertEqual(self.client.get("/doctors").status_code, 403)
        response = self.client.get("/appointments")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Bệnh nhân Một".encode(), response.data)
        self.assertNotIn("Bệnh nhân Hai".encode(), response.data)

        token = self.csrf_token("/appointments")
        status_response = self.client.post(
            f"/appointments/{self.other_appointment.id}/status",
            data={"csrf_token": token, "status": "completed"},
        )
        edit_response = self.client.post(
            f"/appointments/{self.other_appointment.id}/edit",
            data={
                "csrf_token": token,
                "patient_id": self.other_patient.id,
                "doctor_id": self.other_doctor.id,
                "appointment_time": "2030-01-03T11:00",
                "reason": "Unauthorized",
            },
        )
        self.assertEqual(status_response.status_code, 403)
        self.assertEqual(edit_response.status_code, 403)

        own_edit = self.client.post(
            f"/appointments/{self.appointment.id}/edit",
            data={"csrf_token": token, "reason": "Đã cập nhật"},
        )
        self.assertEqual(own_edit.status_code, 302)
        db.session.refresh(self.appointment)
        self.assertEqual(self.appointment.reason, "Đã cập nhật")
        self.assertEqual(self.appointment.doctor_id, self.doctor.id)

    def test_receptionist_cannot_delete_patients_or_doctors(self):
        self.login("frontdesk")
        token = self.csrf_token("/patients")
        patient_response = self.client.post(
            f"/patients/{self.other_patient.id}/delete",
            data={"csrf_token": token},
        )
        doctor_response = self.client.post(
            f"/doctors/{self.other_doctor.id}/delete",
            data={"csrf_token": token},
        )
        self.assertEqual(patient_response.status_code, 403)
        self.assertEqual(doctor_response.status_code, 403)

    def test_existing_receptionist_patient_and_appointment_workflows(self):
        self.login("frontdesk")
        self.assertEqual(self.client.get("/doctors").status_code, 200)
        token = self.csrf_token("/patients")
        create_patient = self.client.post(
            "/patients",
            data={
                "csrf_token": token,
                "full_name": "Bệnh nhân Mới",
                "phone": "0900000000",
                "date_of_birth": "",
            },
        )
        self.assertEqual(create_patient.status_code, 302)
        new_patient = Patient.query.filter_by(full_name="Bệnh nhân Mới").first()
        self.assertIsNotNone(new_patient)

        create_appointment = self.client.post(
            "/appointments",
            data={
                "csrf_token": token,
                "patient_id": new_patient.id,
                "doctor_id": self.doctor.id,
                "appointment_time": "2030-02-01T09:30",
                "reason": "Tái khám",
            },
        )
        self.assertEqual(create_appointment.status_code, 302)
        self.assertEqual(
            Appointment.query.filter_by(patient_id=new_patient.id).count(), 1
        )

    def test_admin_can_create_edit_and_delete_doctor_profiles(self):
        self.login("admin")
        token = self.csrf_token("/doctors")
        response = self.client.post(
            "/doctors",
            data={
                "csrf_token": token,
                "full_name": "Bác sĩ thử",
                "specialty": "Da liễu",
                "phone": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        doctor = Doctor.query.filter_by(full_name="Bác sĩ thử").one()
        token = self.csrf_token("/doctors")
        response = self.client.post(
            f"/doctors/{doctor.id}/edit",
            data={
                "csrf_token": token,
                "full_name": "Bác sĩ đã sửa",
                "specialty": "Da liễu",
                "phone": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        db.session.refresh(doctor)
        self.assertEqual(doctor.full_name, "Bác sĩ đã sửa")
        response = self.client.post(
            f"/doctors/{doctor.id}/delete",
            data={"csrf_token": token},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(db.session.get(Doctor, doctor.id))

    def test_state_changes_require_csrf(self):
        response = self.client.post(
            "/login", data={"username": "admin", "password": "bad-password"}
        )
        self.assertEqual(response.status_code, 400)

        self.login("admin")
        response = self.client.post("/logout")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
