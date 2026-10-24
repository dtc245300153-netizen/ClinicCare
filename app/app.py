
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlsplit

import click
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

from database import db, init_database

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ["FLASK_SECRET_KEY"],
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    ),
)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Vui lòng đăng nhập để tiếp tục."
login_manager.login_message_category = "error"

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


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    doctor_id = db.Column(
        db.Integer, db.ForeignKey("doctors.id"), unique=True
    )
    doctor = db.relationship("Doctor")

    ROLES = ("Admin", "Doctor", "Receptionist")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


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


@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    return user if user and user.is_active else None


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorate


def assigned_appointments():
    query = Appointment.query
    if current_user.role == "Doctor":
        if not current_user.doctor_id:
            abort(403)
        query = query.filter_by(doctor_id=current_user.doctor_id)
    return query


def get_scoped_appointment(appointment_id):
    appointment = db.session.get(Appointment, appointment_id)
    if not appointment:
        return None
    if current_user.role == "Doctor" and (
        appointment.doctor_id != current_user.doctor_id
    ):
        abort(403)
    return appointment


def valid_password(password):
    return 12 <= len(password) <= 128


def valid_username(username):
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", username))


def safe_next_url(target):
    if not target:
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


@app.get("/login")
@app.post("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            login_user(user, fresh=True)
            logger.info("User logged in: id=%s", user.id)
            return redirect(
                safe_next_url(request.args.get("next")) or url_for("dashboard")
            )
        flash("Tên đăng nhập hoặc mật khẩu không đúng.", "error")

    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    logger.info("User logged out: id=%s", current_user.id)
    logout_user()
    flash("Bạn đã đăng xuất.", "success")
    return redirect(url_for("login"))


@app.errorhandler(403)
def forbidden(_error):
    return render_template("403.html"), 403


@app.get("/admin/users")
@roles_required("Admin")
def manage_users():
    users = User.query.order_by(User.created_at.desc(), User.id.desc()).all()
    doctors = Doctor.query.order_by(Doctor.full_name).all()
    return render_template("users.html", users=users, doctors=doctors)


@app.post("/admin/users")
@roles_required("Admin")
def create_user():
    username = request.form.get("username", "").strip().lower()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "")
    doctor_id_value = request.form.get("doctor_id", "").strip()

    if not valid_username(username):
        flash("Tên đăng nhập phải dài 3–80 ký tự, chỉ gồm chữ, số, ., _ hoặc -.", "error")
    elif User.query.filter_by(username=username).first():
        flash("Tên đăng nhập đã tồn tại.", "error")
    elif not full_name or len(full_name) > 150:
        flash("Họ tên là bắt buộc và không được quá 150 ký tự.", "error")
    elif role not in User.ROLES:
        flash("Vai trò không hợp lệ.", "error")
    elif not valid_password(password):
        flash("Mật khẩu phải dài từ 12 đến 128 ký tự.", "error")
    else:
        try:
            doctor_id = int(doctor_id_value) if doctor_id_value else None
        except ValueError:
            doctor_id = -1

        doctor = db.session.get(Doctor, doctor_id) if doctor_id else None
        if role == "Doctor" and not doctor:
            flash("Tài khoản bác sĩ phải được gắn với hồ sơ bác sĩ hợp lệ.", "error")
        elif role != "Doctor" and doctor_id_value:
            flash("Chỉ tài khoản bác sĩ mới được gắn hồ sơ bác sĩ.", "error")
        elif doctor_id and User.query.filter_by(doctor_id=doctor_id).first():
            flash("Hồ sơ bác sĩ này đã được gắn với tài khoản khác.", "error")
        else:
            user = User(
                username=username,
                full_name=full_name,
                role=role,
                is_active=True,
                doctor=doctor if role == "Doctor" else None,
            )
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.commit()
                logger.info("User created: id=%s role=%s", user.id, user.role)
                flash("Tạo tài khoản thành công.", "success")
            except IntegrityError:
                db.session.rollback()
                logger.warning("User creation violated a database constraint")
                flash("Tên đăng nhập hoặc hồ sơ bác sĩ đã được sử dụng.", "error")

    return redirect(url_for("manage_users"))


@app.post("/admin/users/<int:user_id>/update")
@roles_required("Admin")
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("Không tìm thấy tài khoản.", "error")
        return redirect(url_for("manage_users"))

    role = request.form.get("role", "")
    active_value = request.form.get("is_active", "")
    doctor_id_value = request.form.get("doctor_id", "").strip()
    if role not in User.ROLES or active_value not in {"true", "false"}:
        flash("Thông tin vai trò hoặc trạng thái không hợp lệ.", "error")
        return redirect(url_for("manage_users"))

    try:
        doctor_id = int(doctor_id_value) if doctor_id_value else None
    except ValueError:
        doctor_id = -1
    doctor = db.session.get(Doctor, doctor_id) if doctor_id else None

    if role == "Doctor" and not doctor:
        flash("Tài khoản bác sĩ phải được gắn với hồ sơ bác sĩ hợp lệ.", "error")
        return redirect(url_for("manage_users"))
    if role != "Doctor" and doctor_id_value:
        flash("Chỉ tài khoản bác sĩ mới được gắn hồ sơ bác sĩ.", "error")
        return redirect(url_for("manage_users"))
    if doctor_id and User.query.filter(
        User.doctor_id == doctor_id, User.id != user.id
    ).first():
        flash("Hồ sơ bác sĩ này đã được gắn với tài khoản khác.", "error")
        return redirect(url_for("manage_users"))

    is_active = active_value == "true"
    if user.role == "Admin" and (role != "Admin" or not is_active):
        admins = (
            User.query.filter_by(role="Admin", is_active=True)
            .with_for_update()
            .all()
        )
        if len(admins) <= 1:
            flash("Không thể hạ quyền hoặc khóa quản trị viên cuối cùng.", "error")
            return redirect(url_for("manage_users"))

    user.role = role
    user.is_active = is_active
    user.doctor = doctor if role == "Doctor" else None
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        logger.warning("User update violated a database constraint: id=%s", user_id)
        flash("Tên đăng nhập hoặc hồ sơ bác sĩ đã được sử dụng.", "error")
        return redirect(url_for("manage_users"))
    logger.info("User updated: id=%s role=%s active=%s", user.id, role, is_active)
    flash("Cập nhật tài khoản thành công.", "success")
    return redirect(url_for("manage_users"))


@app.cli.command("create-admin")
def create_admin():
    """Create the first administrator using hidden password prompts."""
    username = click.prompt("Tên đăng nhập").strip().lower()
    full_name = click.prompt("Họ và tên").strip()
    password = click.prompt("Mật khẩu (tối thiểu 12 ký tự)", hide_input=True)
    confirmation = click.prompt("Nhập lại mật khẩu", hide_input=True)

    if not valid_username(username):
        raise click.ClickException(
            "Tên đăng nhập phải dài 3–80 ký tự và chỉ gồm chữ, số, ., _ hoặc -."
        )
    if not full_name or len(full_name) > 150:
        raise click.ClickException("Họ tên không hợp lệ.")
    if not valid_password(password):
        raise click.ClickException("Mật khẩu phải dài từ 12 đến 128 ký tự.")
    if password != confirmation:
        raise click.ClickException("Hai mật khẩu không khớp.")
    if User.query.filter_by(username=username).first():
        raise click.ClickException("Tên đăng nhập đã tồn tại.")
    if User.query.filter_by(role="Admin", is_active=True).first():
        raise click.ClickException("Đã có quản trị viên đang hoạt động.")

    user = User(username=username, full_name=full_name, role="Admin")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo("Đã tạo tài khoản quản trị viên.")


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
@login_required
def index():
    return redirect(url_for("dashboard"))

@app.get("/dashboard")
@roles_required("Admin", "Doctor", "Receptionist")
def dashboard():
    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)
    week_start = today_start - timedelta(days=6)

    daily_query = db.session.query(
        func.date(Appointment.appointment_time),
        Appointment.status,
        func.count(Appointment.id)
    )
    today_query = Appointment.query
    appointment_query = Appointment.query
    status_query = db.session.query(
        Appointment.status, func.count(Appointment.id)
    )
    upcoming_query = Appointment.query
    if current_user.role == "Doctor":
        if not current_user.doctor_id:
            abort(403)
        daily_query = daily_query.filter(
            Appointment.doctor_id == current_user.doctor_id
        )
        today_query = today_query.filter_by(doctor_id=current_user.doctor_id)
        appointment_query = appointment_query.filter_by(
            doctor_id=current_user.doctor_id
        )
        status_query = status_query.filter(
            Appointment.doctor_id == current_user.doctor_id
        )
        upcoming_query = upcoming_query.filter_by(
            doctor_id=current_user.doctor_id
        )

    daily_counts = {}
    for appointment_date, status, count in (
        daily_query
        .filter(Appointment.appointment_time >= week_start)
        .filter(Appointment.appointment_time < tomorrow_start)
        .group_by(func.date(Appointment.appointment_time), Appointment.status)
        .all()
    ):
        daily_counts.setdefault(appointment_date, {})[status] = count

    chart_statuses = ("scheduled", "completed", "cancelled")
    chart_days = []
    for offset in range(7):
        day = (week_start + timedelta(days=offset)).date()
        counts = daily_counts.get(day, {})
        chart_days.append({
            "date": day,
            "label": day.strftime("%d/%m"),
            "scheduled": counts.get("scheduled", 0),
            "completed": counts.get("completed", 0),
            "cancelled": counts.get("cancelled", 0),
            "total": sum(counts.get(status, 0) for status in chart_statuses)
        })

    appointments_today = today_query.filter(
        Appointment.appointment_time >= today_start,
        Appointment.appointment_time < tomorrow_start
    ).count()
    upcoming_appointments = upcoming_query.filter(
        Appointment.appointment_time >= datetime.now(),
        Appointment.status == "scheduled"
    ).order_by(Appointment.appointment_time.asc()).limit(5).all()

    patient_count = Patient.query.count()
    if current_user.role == "Doctor":
        patient_count = (
            db.session.query(func.count(func.distinct(Appointment.patient_id)))
            .filter(Appointment.doctor_id == current_user.doctor_id)
            .scalar()
        )

    return render_template(
        "dashboard.html",
        patient_count=patient_count,
        doctor_count=Doctor.query.count(),
        appointment_count=appointment_query.count(),
        appointments_today=appointments_today,
        chart_days=chart_days,
        max_daily_count=max((day["total"] for day in chart_days), default=0) or 1,
        status_counts=dict(
            status_query
            .group_by(Appointment.status)
            .all()
        ),
        upcoming_appointments=upcoming_appointments
    )


@app.get("/patients")
@roles_required("Admin", "Receptionist")
def patients():
    patient_list = Patient.query.order_by(Patient.id.desc()).all()
    return render_template("patients.html", patients=patient_list)


@app.post("/patients")
@roles_required("Admin", "Receptionist")
def create_patient():
    name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip()
    dob = request.form.get("date_of_birth", "").strip()

    if not name:
        flash("Họ tên bệnh nhân là bắt buộc.", "error")
    else:
        try:
            date_of_birth = (
                datetime.strptime(dob, "%Y-%m-%d").date() if dob else None
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


@app.post("/patients/<int:patient_id>/delete")
@roles_required("Admin")
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


@app.post("/patients/<int:patient_id>/edit")
@roles_required("Admin", "Receptionist")
def edit_patient(patient_id):
    patient = db.session.get(Patient, patient_id)
    name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip()
    dob = request.form.get("date_of_birth", "").strip()

    if not patient:
        flash("Không tìm thấy bệnh nhân.", "error")
    elif not name:
        flash("Họ tên bệnh nhân là bắt buộc.", "error")
    else:
        try:
            patient.full_name = name
            patient.phone = phone or None
            patient.date_of_birth = (
                datetime.strptime(dob, "%Y-%m-%d").date() if dob else None
            )
            db.session.commit()
            logger.info("Patient updated: id=%s", patient_id)
            flash("Cập nhật bệnh nhân thành công.", "success")
        except ValueError:
            db.session.rollback()
            flash("Ngày sinh không hợp lệ.", "error")

    return redirect(url_for("patients"))


@app.get("/doctors")
@roles_required("Admin", "Receptionist")
def doctors():
    doctor_list = Doctor.query.order_by(Doctor.id.desc()).all()
    return render_template("doctors.html", doctors=doctor_list)


@app.post("/doctors")
@roles_required("Admin")
def create_doctor():
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


@app.post("/doctors/<int:doctor_id>/delete")
@roles_required("Admin")
def delete_doctor(doctor_id):
    doctor = db.session.get(Doctor, doctor_id)

    if not doctor:
        flash("Không tìm thấy bác sĩ.", "error")
    elif Appointment.query.filter_by(doctor_id=doctor_id).first():
        flash("Bác sĩ đã có lịch khám, không thể xóa.", "error")
    elif User.query.filter_by(doctor_id=doctor_id).first():
        flash("Bác sĩ đã được gắn với tài khoản người dùng, không thể xóa.", "error")
    else:
        db.session.delete(doctor)
        db.session.commit()

        logger.info("Doctor deleted: id=%s", doctor_id)
        flash("Xóa bác sĩ thành công.", "success")

    return redirect(url_for("doctors"))


@app.post("/doctors/<int:doctor_id>/edit")
@roles_required("Admin")
def edit_doctor(doctor_id):
    doctor = db.session.get(Doctor, doctor_id)
    name = request.form.get("full_name", "").strip()
    specialty = request.form.get("specialty", "").strip()
    phone = request.form.get("phone", "").strip()

    if not doctor:
        flash("Không tìm thấy bác sĩ.", "error")
    elif not name or not specialty:
        flash("Họ tên và chuyên khoa là bắt buộc.", "error")
    else:
        doctor.full_name = name
        doctor.specialty = specialty
        doctor.phone = phone or None
        db.session.commit()
        logger.info("Doctor updated: id=%s", doctor_id)
        flash("Cập nhật bác sĩ thành công.", "success")

    return redirect(url_for("doctors"))


@app.get("/appointments")
@roles_required("Admin", "Doctor", "Receptionist")
def appointments():
    appointment_list = assigned_appointments().order_by(
        Appointment.appointment_time.desc()
    ).all()

    if current_user.role == "Doctor":
        patient_list = (
            Patient.query.join(Appointment)
            .filter(Appointment.doctor_id == current_user.doctor_id)
            .distinct()
            .order_by(Patient.full_name)
            .all()
        )
        doctor_list = [current_user.doctor] if current_user.doctor else []
    else:
        patient_list = Patient.query.order_by(Patient.full_name).all()
        doctor_list = Doctor.query.order_by(Doctor.full_name).all()

    return render_template(
        "appointments.html",
        appointments=appointment_list,
        patients=patient_list,
        doctors=doctor_list
    )


@app.post("/appointments")
@roles_required("Admin", "Receptionist")
def create_appointment():
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

@app.post("/appointments/<int:appointment_id>/status")
@roles_required("Admin", "Doctor", "Receptionist")
def update_appointment_status(appointment_id):
    appointment = get_scoped_appointment(appointment_id)
    status = request.form.get("status", "")

    valid_statuses = {"scheduled", "completed", "cancelled"}
    if current_user.role == "Receptionist":
        valid_statuses = {"scheduled", "cancelled"}
    elif current_user.role == "Doctor":
        valid_statuses = {"completed", "cancelled"}

    if not appointment:
        flash("Không tìm thấy lịch khám.", "error")
    elif status in {"scheduled", "completed", "cancelled"} and status not in valid_statuses:
        abort(403)
    elif current_user.role in {"Doctor", "Receptionist"} and (
        appointment.status != "scheduled"
    ):
        abort(403)
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


@app.post("/appointments/<int:appointment_id>/edit")
@roles_required("Admin", "Doctor", "Receptionist")
def edit_appointment(appointment_id):
    appointment = get_scoped_appointment(appointment_id)

    if current_user.role == "Doctor":
        if not appointment:
            flash("Không tìm thấy lịch khám.", "error")
        else:
            appointment.reason = request.form.get("reason", "").strip() or None
            db.session.commit()
            logger.info("Appointment note updated: id=%s", appointment_id)
            flash("Cập nhật ghi chú lịch khám thành công.", "success")
        return redirect(url_for("appointments"))

    try:
        patient_id = int(request.form["patient_id"])
        doctor_id = int(request.form["doctor_id"])
        appointment_time = datetime.strptime(
            request.form["appointment_time"],
            "%Y-%m-%dT%H:%M"
        )
    except (ValueError, KeyError):
        flash("Thông tin lịch khám không hợp lệ.", "error")
        return redirect(url_for("appointments"))

    if not appointment:
        flash("Không tìm thấy lịch khám.", "error")
    elif current_user.role == "Receptionist" and appointment.status != "scheduled":
        abort(403)
    elif not db.session.get(Patient, patient_id):
        flash("Không tìm thấy bệnh nhân.", "error")
    elif not db.session.get(Doctor, doctor_id):
        flash("Không tìm thấy bác sĩ.", "error")
    else:
        appointment.patient_id = patient_id
        appointment.doctor_id = doctor_id
        appointment.appointment_time = appointment_time
        appointment.reason = request.form.get("reason", "").strip() or None
        db.session.commit()
        logger.info("Appointment updated: id=%s", appointment_id)
        flash("Cập nhật lịch khám thành công.", "success")

    return redirect(url_for("appointments"))
