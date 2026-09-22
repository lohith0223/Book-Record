import io
import os
from functools import wraps
from datetime import datetime, timezone

import qrcode
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, or_, text
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to access the reading desk."
migrate = Migrate()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), default="librarian", nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return f"admin:{self.id}"


@login_manager.user_loader
def load_user(user_id):
    kind, record_id = user_id.split(":", 1)
    model = User if kind == "admin" else Student
    return db.session.get(model, int(record_id))


class Stand(db.Model):
    __tablename__ = "stands"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    floor = db.Column(db.Integer, nullable=False)
    zone = db.Column(db.String(80), nullable=False)
    stand_number = db.Column(db.String(20))
    classroom = db.Column(db.String(120))
    description = db.Column(db.String(255))
    books = db.relationship("Book", backref="stand", lazy=True, cascade="all, delete-orphan")
    
    @property
    def floor_label(self):
        return f"{self.floor}th Floor" if self.floor not in {3, 4} else f"{self.floor}rd Floor" if self.floor == 3 else "4th Floor"


class Student(UserMixin, db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(30), unique=True, nullable=False)
    usn = db.Column(db.String(40), unique=True)
    name = db.Column(db.String(120), nullable=False)
    full_name = db.Column(db.String(120))
    program = db.Column(db.String(80), default="MBA")
    email = db.Column(db.String(120))
    college_email = db.Column(db.String(160), unique=True)
    phone = db.Column(db.String(30))
    course = db.Column(db.String(80), default="MBA")
    semester = db.Column(db.String(30))
    section = db.Column(db.String(30))
    password_hash = db.Column(db.String(255))
    account_status = db.Column(db.String(20), default="active", nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)

    def get_id(self):
        return f"student:{self.id}"

    @property
    def role(self):
        return "student"


class Book(db.Model):
    __tablename__ = "books"
    id = db.Column(db.Integer, primary_key=True)
    book_code = db.Column(db.String(40), unique=True, nullable=False)
    title = db.Column(db.String(180), nullable=False)
    author = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    isbn = db.Column(db.String(30))
    description = db.Column(db.Text)
    stand_id = db.Column(db.Integer, db.ForeignKey("stands.id"), nullable=False)
    status = db.Column(db.String(20), default="AVAILABLE", nullable=False)
    scan_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    events = db.relationship("Activity", backref="book", lazy=True, cascade="all, delete-orphan")
    loans = db.relationship("Loan", backref="book", lazy=True, cascade="all, delete-orphan")


class Activity(db.Model):
    __tablename__ = "activities"
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(30), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"))
    student_name = db.Column(db.String(120))
    note = db.Column(db.String(255))
    occurred_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    student = db.relationship("Student", backref="activities")


class Loan(db.Model):
    __tablename__ = "loans"
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    borrowed_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    returned_at = db.Column(db.DateTime)
    student = db.relationship("Student", backref="loans")

    @property
    def duration_days(self):
        return max(0, ((self.returned_at or utcnow()) - self.borrowed_at).days)


def upgrade_existing_schema():
    """Add fields introduced after the first local SQLite database was created."""
    inspector = inspect(db.engine)
    additions = {
        "stands": {"stand_number": "VARCHAR(20)", "classroom": "VARCHAR(120)"},
        "students": {
            "usn": "VARCHAR(40)", "full_name": "VARCHAR(120)", "college_email": "VARCHAR(160)",
            "phone": "VARCHAR(30)", "course": "VARCHAR(80)", "semester": "VARCHAR(30)",
            "section": "VARCHAR(30)", "password_hash": "VARCHAR(255)", "account_status": "VARCHAR(20)",
        },
        "books": {"description": "TEXT"},
    }
    with db.engine.begin() as connection:
        for table, columns in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table)}
            for column, column_type in columns.items():
                if column not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))
        connection.execute(text("UPDATE students SET full_name = name WHERE full_name IS NULL"))
        connection.execute(text("UPDATE students SET college_email = email WHERE college_email IS NULL AND email IS NOT NULL"))
        connection.execute(text("UPDATE students SET course = program WHERE course IS NULL AND program IS NOT NULL"))
        connection.execute(text("UPDATE students SET account_status = 'active' WHERE account_status IS NULL"))
        connection.execute(text("UPDATE books SET status = UPPER(status) WHERE status IN ('available', 'reading', 'borrowed')"))
        connection.execute(text("UPDATE stands SET stand_number = code WHERE stand_number IS NULL"))
        connection.execute(text("UPDATE stands SET classroom = zone WHERE classroom IS NULL"))
        legacy_stands = connection.execute(text("SELECT id, floor, code FROM stands WHERE code LIKE 'S-%' ORDER BY id")).fetchall()
        for stand_id, floor, old_code in legacy_stands:
            number = old_code.split("-")[-1]
            new_code = f"{floor}F-S{int(number):02d}"
            connection.execute(text("UPDATE stands SET code = :code, stand_number = :number WHERE id = :id"), {"code": new_code, "number": number, "id": stand_id})


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///mba_reading_stand.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    with app.app_context():
        db.create_all()
        upgrade_existing_schema()
        seed_data()
    register_routes(app)
    return app


def seed_data():
    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", role="librarian")
        admin.set_password(os.getenv("ADMIN_PASSWORD", "admin123"))
        db.session.add(admin)
    if Stand.query.first():
        db.session.commit()
        return
    specs = [(f"{floor}F-S{i:02d}", floor, "North Wing" if i % 2 else "Learning Commons") for floor in (3, 4) for i in range(1, 8)]
    stands = [Stand(code=code, floor=floor, stand_number=code, classroom=classroom, zone=classroom, description=f"Floor {floor} reading stand") for code, floor, classroom in specs]
    db.session.add_all(stands)
    db.session.flush()
    books = [("Strategic Management", "Fred David", "Strategy"), ("Marketing Management", "Philip Kotler", "Marketing"), ("Financial Management", "Eugene Brigham", "Finance"), ("Organizational Behavior", "Stephen Robbins", "Leadership"), ("Operations Management", "Jay Heizer", "Operations"), ("Business Research Methods", "Donald Cooper", "Research"), ("The Lean Startup", "Eric Ries", "Innovation"), ("Good to Great", "Jim Collins", "Leadership")]
    for index, stand in enumerate(stands):
        for slot in range(6 + (1 if index == 0 else 0)):
            title, author, category = books[(index * 2 + slot) % len(books)]
            db.session.add(Book(book_code=f"MBA-{stand.code}-{slot + 1:02d}", title=title, author=author, category=category, stand_id=stand.id))
    db.session.commit()


def get_or_create_student(student_id, name):
    student_id = student_id.strip().upper()
    student = Student.query.filter_by(student_id=student_id).first()
    if student:
        student.name = name.strip() or student.name
        return student
    student = Student(student_id=student_id, name=name.strip() or "Unknown student", full_name=name.strip() or "Unknown student", account_status="active")
    db.session.add(student)
    db.session.flush()
    return student


def record_event(book, event_type, student=None, note=None):
    if event_type == "view":
        book.scan_count += 1
    db.session.add(Activity(event_type=event_type, book_id=book.id, student_id=student.id if student else None, student_name=student.name if student else None, note=note))


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if getattr(current_user, "role", None) != "librarian":
            flash("This area is restricted to administrators.", "warning")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped


def register_routes(app):
    @app.context_processor
    def inject_helpers():
        return {"now": utcnow}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = User.query.filter_by(username=username).first()
            student = Student.query.filter(or_(Student.student_id == username.upper(), Student.usn == username.upper(), Student.college_email == username.lower())).first()
            identity = user if user and user.check_password(password) else student if student and student.account_status == "active" and student.check_password(password) else None
            if identity:
                login_user(identity)
                return redirect(request.args.get("next") or url_for("dashboard"))
            flash("Invalid username or password.", "warning")
        return render_template("login.html")

    @app.get("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def dashboard():
        if getattr(current_user, "role", None) == "student":
            active_loans = Loan.query.filter_by(student_id=current_user.id, returned_at=None).order_by(Loan.borrowed_at.desc()).all()
            return render_template("student_dashboard.html", student=current_user, active_loans=active_loans)
        stats = {"books": Book.query.count(), "available": Book.query.filter_by(status="AVAILABLE").count(), "borrowed": Book.query.filter_by(status="BORROWED").count(), "students": Student.query.count(), "scans": db.session.query(func.coalesce(func.sum(Book.scan_count), 0)).scalar()}
        popular = Book.query.order_by(Book.scan_count.desc()).limit(5).all()
        floor_rows = db.session.query(Stand.floor, func.count(Activity.id)).join(Book, Book.stand_id == Stand.id).outerjoin(Activity, Activity.book_id == Book.id).group_by(Stand.floor).order_by(Stand.floor).all()
        stand_rows = db.session.query(Stand.code, func.count(Activity.id)).join(Book, Book.stand_id == Stand.id).outerjoin(Activity, Activity.book_id == Book.id).group_by(Stand.code).order_by(func.count(Activity.id).desc()).limit(14).all()
        recent = Activity.query.order_by(Activity.occurred_at.desc()).limit(8).all()
        return render_template("dashboard.html", stats=stats, popular=popular, floor_rows=floor_rows, stand_rows=stand_rows, recent=recent)

    @app.get("/books")
    @admin_required
    def books():
        query = Book.query
        search, status, floor = request.args.get("q", "").strip(), request.args.get("status", ""), request.args.get("floor", "")
        if search:
            query = query.filter(or_(Book.title.ilike(f"%{search}%"), Book.book_code.ilike(f"%{search}%"), Book.author.ilike(f"%{search}%")))
        if status:
            query = query.filter_by(status=status.upper())
        if floor in {"3", "4"}:
            query = query.join(Stand).filter(Stand.floor == int(floor))
        return render_template("books.html", books=query.order_by(Book.title).all(), search=search, status=status, floor=floor)

    @app.get("/stands")
    @admin_required
    def stands():
        stand_list = Stand.query.order_by(Stand.floor, Stand.code).all()
        for stand in stand_list:
            stand.interaction_count = sum(book.scan_count + sum(1 for event in book.events if event.event_type in {"borrow", "return"}) for book in stand.books)
        return render_template("stands.html", stands=stand_list)

    @app.route("/stands/new", methods=["GET", "POST"])
    @admin_required
    def create_stand():
        if request.method == "POST":
            floor = request.form.get("floor", "").strip()
            stand_number = request.form.get("stand_number", "").strip().upper()
            classroom = request.form.get("classroom", "").strip()
            description = request.form.get("description", "").strip()
            if floor not in {"3", "4"} or not stand_number or not classroom:
                flash("Floor, stand number, and classroom are required.", "warning")
            else:
                code = f"{floor}F-S{int(stand_number):02d}" if stand_number.isdigit() else stand_number
                if Stand.query.filter_by(code=code).first():
                    flash(f"Stand {code} already exists.", "warning")
                else:
                    db.session.add(Stand(code=code, floor=int(floor), stand_number=stand_number, classroom=classroom, zone=classroom, description=description))
                    db.session.commit()
                    flash(f"Stand {code} created successfully.", "success")
                    return redirect(url_for("stands"))
        return render_template("stand_form.html")

    @app.get("/students")
    @admin_required
    def students():
        student_list = Student.query.order_by(Student.name).all()
        for student in student_list:
            student.view_count = sum(1 for event in student.activities if event.event_type == "view")
            student.loan_count = len(student.loans)
        return render_template("students.html", students=student_list)

    @app.route("/students/new", methods=["GET", "POST"])
    @admin_required
    def create_student():
        if request.method == "POST":
            form = {key: request.form.get(key, "").strip() for key in ("student_id", "usn", "full_name", "college_email", "phone", "course", "semester", "section", "password")}
            required = ("student_id", "usn", "full_name", "college_email", "course", "semester", "section", "password")
            if not all(form[key] for key in required):
                flash("Student ID, USN, name, email, course, semester, section, and password are required.", "warning")
            elif Student.query.filter(or_(Student.student_id == form["student_id"].upper(), Student.usn == form["usn"].upper(), Student.college_email == form["college_email"].lower())).first():
                flash("Student ID, USN, or college email is already registered.", "warning")
            else:
                student = Student(student_id=form["student_id"].upper(), usn=form["usn"].upper(), name=form["full_name"], full_name=form["full_name"], email=form["college_email"].lower(), college_email=form["college_email"].lower(), phone=form["phone"], course=form["course"], program=form["course"], semester=form["semester"], section=form["section"], account_status="active")
                student.set_password(form["password"])
                db.session.add(student)
                db.session.commit()
                flash(f"Student {student.student_id} created with a securely hashed password.", "success")
                return redirect(url_for("students"))
        return render_template("student_form.html")

    @app.route("/books/new", methods=["GET", "POST"])
    @admin_required
    def create_book():
        stands = Stand.query.order_by(Stand.floor, Stand.code).all()
        if request.method == "POST":
            book_code = request.form.get("book_code", "").strip().upper()
            stand = db.session.get(Stand, request.form.get("stand_id", type=int))
            status = request.form.get("status", "AVAILABLE").upper()
            if status not in {"AVAILABLE", "READING", "BORROWED"}:
                status = "AVAILABLE"
            if not book_code or not request.form.get("title", "").strip() or not request.form.get("author", "").strip() or not request.form.get("category", "").strip() or not stand:
                flash("Book ID, title, author, category, and stand are required.", "warning")
            elif Book.query.filter_by(book_code=book_code).first():
                flash("Book ID must be unique.", "warning")
            else:
                db.session.add(Book(book_code=book_code, title=request.form["title"].strip(), author=request.form["author"].strip(), isbn=request.form.get("isbn", "").strip() or None, category=request.form["category"].strip(), description=request.form.get("description", "").strip(), stand_id=stand.id, status=status))
                db.session.commit()
                flash(f"Book {book_code} created and assigned to {stand.code}.", "success")
                return redirect(url_for("books"))
        return render_template("book_form.html", stands=stands)

    @app.get("/books/<book_code>")
    @admin_required
    def book_detail(book_code):
        book = Book.query.filter_by(book_code=book_code).first_or_404()
        history = Activity.query.filter_by(book_id=book.id).order_by(Activity.occurred_at.desc()).limit(15).all()
        active_loan = Loan.query.filter_by(book_id=book.id, returned_at=None).first()
        return render_template("book_detail.html", book=book, history=history, active_loan=active_loan)

    @app.get("/books/<book_code>/qr.png")
    @admin_required
    def book_qr(book_code):
        book = Book.query.filter_by(book_code=book_code).first_or_404()
        image = qrcode.make(url_for("scan_book", book_code=book.book_code, _external=True))
        output = io.BytesIO()
        image.save(output, format="PNG")
        output.seek(0)
        return send_file(output, mimetype="image/png")

    @app.route("/scan/<book_code>", methods=["GET", "POST"])
    def scan_book(book_code):
        book = Book.query.filter_by(book_code=book_code).first_or_404()
        if request.method == "POST":
            student_id, name = request.form.get("student_id", "").strip(), request.form.get("name", "").strip()
            if not student_id or not name:
                flash("Student ID and name are required to record a view.", "warning")
            else:
                student = get_or_create_student(student_id, name)
                record_event(book, "view", student, "QR scan / book view")
                db.session.commit()
                flash("Your reading activity has been recorded.", "success")
                return redirect(url_for("scan_book", book_code=book.book_code))
        return render_template("scan.html", book=book)

    @app.route("/student/borrow", methods=["GET", "POST"])
    def student_borrow():
        available_books = Book.query.filter_by(status="AVAILABLE").order_by(Book.title).all()
        if request.method == "POST":
            book = db.session.get(Book, request.form.get("book_id", type=int))
            student_id = request.form.get("student_id", "").strip()
            name = request.form.get("name", "").strip()
            if not book or book.status != "AVAILABLE":
                flash("That book is no longer available. Please choose another title.", "warning")
            elif not student_id or not name:
                flash("Student ID and full name are required.", "warning")
            else:
                student = get_or_create_student(student_id, name)
                book.status = "BORROWED"
                db.session.add(Loan(book=book, student=student))
                record_event(book, "borrow", student, "Student self-service borrowing request")
                db.session.commit()
                flash(f"{book.title} has been borrowed by {student.name}.", "success")
                return redirect(url_for("student_borrow"))
        return render_template("student_borrow.html", available_books=available_books)

    @app.post("/books/<book_code>/borrow")
    @admin_required
    def borrow_book(book_code):
        book = Book.query.filter_by(book_code=book_code).first_or_404()
        if book.status != "AVAILABLE":
            flash("This book is already borrowed.", "warning")
        else:
            student_id, name = request.form.get("student_id", ""), request.form.get("name", "")
            if not student_id or not name:
                flash("Student ID and name are required.", "warning")
            else:
                student = get_or_create_student(student_id, name)
                book.status = "BORROWED"
                db.session.add(Loan(book=book, student=student))
                record_event(book, "borrow", student, "Book borrowed")
                db.session.commit()
                flash("Book issued successfully.", "success")
        return redirect(url_for("book_detail", book_code=book_code))

    @app.post("/books/<book_code>/return")
    @admin_required
    def return_book(book_code):
        book = Book.query.filter_by(book_code=book_code).first_or_404()
        loan = Loan.query.filter_by(book_id=book.id, returned_at=None).first()
        if loan:
            loan.returned_at, book.status = utcnow(), "AVAILABLE"
            record_event(book, "return", loan.student, "Book returned")
            db.session.commit()
            flash("Book returned and marked available.", "success")
        return redirect(url_for("book_detail", book_code=book_code))

    @app.get("/history")
    @admin_required
    def history():
        return render_template("history.html", events=Activity.query.order_by(Activity.occurred_at.desc()).limit(200).all())

    @app.get("/loans")
    @admin_required
    def loans():
        active_loans = Loan.query.filter_by(returned_at=None).order_by(Loan.borrowed_at.desc()).all()
        returned_loans = Loan.query.filter(Loan.returned_at.is_not(None)).order_by(Loan.returned_at.desc()).limit(100).all()
        return render_template("loans.html", active_loans=active_loans, returned_loans=returned_loans)

    @app.get("/api/summary")
    @admin_required
    def api_summary():
        return jsonify({"books": Book.query.count(), "available": Book.query.filter_by(status="AVAILABLE").count(), "borrowed": Book.query.filter_by(status="BORROWED").count(), "scans": db.session.query(func.coalesce(func.sum(Book.scan_count), 0)).scalar()})


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)