
import logging
import os
import time
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash
from sqlalchemy import text
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from database import db, init_database

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("clinic")

REQUESTS = Counter(
    "clinic_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)
LATENCY = Histogram(
    "clinic_http_request_duration_seconds",
    "HTTP request duration"
)

init_database(app)


class Patient(db.Model):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    date_of_birth = db.Column(db.Date)
    phone = db.Column(db.String(20))


class Doctor(db.Model):
    __tablename__ = "doctors"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    specialty = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))


class Appointment(db.Model):
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(
        db.Integer, db.ForeignKey("patients.id"), nullable=False
    )
    doctor_id = db.Column(
        db.Integer, db.ForeignKey("doctors.id"), nullable=False
    )
    appointment_time = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(
        db.String(30), nullable=False, default="scheduled"
    )

    patient = db.relationship("Patient")
    doctor = db.relationship("Doctor")


@app.before_request
def start_timer():
    request.start_time = time.perf_counter()


@app.after_request
def record_request(response):
    if request.path != "/metrics":
        duration = time.perf_counter() - getattr(
            request, "start_time", time.perf_counter()
        )

        REQUESTS.labels(
            request.method,
            request.endpoint or "unknown",
            str(response.status_code)
        ).inc()

        LATENCY.observe(duration)

    return response


@app.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}, 200
    except Exception:
        db.session.rollback()
        logger.exception("Database health check failed")
        return {"status": "error", "database": "unavailable"}, 503


@app.get("/metrics")
def metrics():
    return (
        generate_latest(),
        200,
        {"Content-Type": CONTENT_TYPE_LATEST}
    )


@app.get("/")
def index():
    return redirect(url_for("patients"))


@app.route("/patients", methods=["GET", "POST"])
def patients():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        dob = request.form.get("date_of_birth", "").strip()

        if not name:
            flash("Họ tên bệnh nhân là bắt buộc.", "error")
        else:
            try:
                date_of_birth = (
                    datetime.strptime(dob, "%Y-%m-%d").date()
                    if dob else None
                )

                patient = Patient(
                    full_name=name,
                    phone=phone or None,
                    date_of_birth=date_of_birth
                )

                db.session.add(patient)
                db.session.commit()

                logger.info("Patient created: id=%s", patient.id)
                flash("Thêm bệnh nhân thành công.", "success")
                return redirect(url_for("patients"))

            except ValueError:
                db.session.rollback()
                flash("Ngày sinh không hợp lệ.", "error")

    patient_list = Patient.query.order_by(Patient.id.desc()).all()
    return render_template("patients.html", patients=patient_list)


@app.post("/patients/<int:patient_id>/delete")
def delete_patient(patient_id):
    patient = db.session.get(Patient, patient_id)

    if not patient:
        flash("Không tìm thấy bệnh nhân.", "error")
    elif Appointment.query.filter_by(patient_id=patient_id).first():
        flash("Bệnh nhân đã có lịch khám, không thể xóa.", "error")
    else:
        db.session.delete(patient)
        db.session.commit()

        logger.info("Patient deleted: id=%s", patient_id)
        flash("Xóa bệnh nhân thành công.", "success")

    return redirect(url_for("patients"))


@app.route("/doctors", methods=["GET", "POST"])
def doctors():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        specialty = request.form.get("specialty", "").strip()
        phone = request.form.get("phone", "").strip()

        if not name or not specialty:
            flash("Họ tên và chuyên khoa là bắt buộc.", "error")
        else:
            doctor = Doctor(
                full_name=name,
                specialty=specialty,
                phone=phone or None
            )

            db.session.add(doctor)
            db.session.commit()

            logger.info("Doctor created: id=%s", doctor.id)
            flash("Thêm bác sĩ thành công.", "success")
            return redirect(url_for("doctors"))

    doctor_list = Doctor.query.order_by(Doctor.id.desc()).all()
    return render_template("doctors.html", doctors=doctor_list)


@app.post("/doctors/<int:doctor_id>/delete")
def delete_doctor(doctor_id):
    doctor = db.session.get(Doctor, doctor_id)

    if not doctor:
        flash("Không tìm thấy bác sĩ.", "error")
    elif Appointment.query.filter_by(doctor_id=doctor_id).first():
        flash("Bác sĩ đã có lịch khám, không thể xóa.", "error")
    else:
        db.session.delete(doctor)
        db.session.commit()

        logger.info("Doctor deleted: id=%s", doctor_id)
        flash("Xóa bác sĩ thành công.", "success")

    return redirect(url_for("doctors"))


@app.route("/appointments", methods=["GET", "POST"])
def appointments():
    if request.method == "POST":
        try:
            patient_id = int(request.form["patient_id"])
            doctor_id = int(request.form["doctor_id"])

            appointment_time = datetime.strptime(
                request.form["appointment_time"],
                "%Y-%m-%dT%H:%M"
            )

            reason = request.form.get("reason", "").strip()

            if not db.session.get(Patient, patient_id):
                raise ValueError("Bệnh nhân không tồn tại.")

            if not db.session.get(Doctor, doctor_id):
                raise ValueError("Bác sĩ không tồn tại.")

            appointment = Appointment(
                patient_id=patient_id,
                doctor_id=doctor_id,
                appointment_time=appointment_time,
                reason=reason or None
            )

            db.session.add(appointment)
            db.session.commit()

            logger.info("Appointment created: id=%s", appointment.id)
            flash("Đặt lịch khám thành công.", "success")
            return redirect(url_for("appointments"))

        except (ValueError, KeyError):
            db.session.rollback()
            flash("Thông tin lịch khám không hợp lệ.", "error")

    appointment_list = Appointment.query.order_by(
        Appointment.appointment_time.desc()
    ).all()

    patient_list = Patient.query.order_by(Patient.full_name).all()
    doctor_list = Doctor.query.order_by(Doctor.full_name).all()

    return render_template(
        "appointments.html",
        appointments=appointment_list,
        patients=patient_list,
        doctors=doctor_list
    )


@app.post("/appointments/<int:appointment_id>/status")
def update_appointment_status(appointment_id):
    appointment = db.session.get(Appointment, appointment_id)
    status = request.form.get("status", "")

    valid_statuses = {"scheduled", "completed", "cancelled"}

    if not appointment:
        flash("Không tìm thấy lịch khám.", "error")
    elif status not in valid_statuses:
        flash("Trạng thái không hợp lệ.", "error")
    else:
        appointment.status = status
        db.session.commit()

        logger.info(
            "Appointment status updated: id=%s status=%s",
            appointment_id,
            status
        )
        flash("Cập nhật trạng thái thành công.", "success")

    return redirect(url_for("appointments"))
