"""StudyTrack: a flexible planner and grade tracker for students.

AI assistance disclosure: ChatGPT helped plan the database structure, create an
initial implementation, and explain testing. The student must review, test,
understand, and personalize the project before submitting it to CS50.
"""

import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "studytrack-development-key")
app.config["DATABASE"] = os.path.join(app.root_path, "studytrack.db")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


@app.before_request
def keep_user_signed_in():
    session.permanent = True

def get_db():
    """Open one database connection for the current request."""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    """Close the current request's database connection."""
    database = g.pop("db", None)
    if database is not None:
        database.close()


def init_db():
    """Create the database tables if this is the first run."""
    database = get_db()
    with open(os.path.join(app.root_path, "schema.sql"), encoding="utf-8") as schema:
        database.executescript(schema.read())
    database.commit()


def login_required(view):
    """Redirect visitors to the landing page when authentication is required."""
    @wraps(view)
    def wrapped_view(**kwargs):
        if session.get("user_id") is None:
            flash("Please log in or continue as a guest.", "warning")
            return redirect(url_for("landing"))
        return view(**kwargs)

    return wrapped_view


def current_user():
    """Return the signed-in user."""
    if session.get("user_id") is None:
        return None
    return get_db().execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()


@app.context_processor
def inject_user():
    """Make the current user available to every template."""
    return {"current_user": current_user()}


def owned_course(course_id):
    """Return a course only if it belongs to the signed-in user."""
    return get_db().execute(
        "SELECT * FROM courses WHERE id = ? AND user_id = ?",
        (course_id, session["user_id"]),
    ).fetchone()


def parse_grade(form):
    """Validate optional earned and maximum point values."""
    score_text = form.get("score", "").strip()
    maximum_text = form.get("max_score", "").strip()

    if not score_text and not maximum_text:
        return None, None
    if not score_text or not maximum_text:
        raise ValueError("Enter both the earned points and maximum points.")

    score = float(score_text)
    maximum = float(maximum_text)
    if score < 0 or maximum <= 0:
        raise ValueError("Grades must use non-negative points and a positive maximum.")
    return score, maximum


def calculate_course_grade(course_id, mode):
    """Calculate either a points-based or category-weighted current grade."""
    database = get_db()
    graded_items = database.execute(
        """
        SELECT category_id, score, max_score
        FROM items
        WHERE course_id = ? AND score IS NOT NULL AND max_score IS NOT NULL
        """,
        (course_id,),
    ).fetchall()

    if not graded_items:
        return None, []

    if mode == "points":
        earned = sum(item["score"] for item in graded_items)
        possible = sum(item["max_score"] for item in graded_items)
        grade = earned / possible * 100 if possible else None
        return grade, []

    categories = database.execute(
        "SELECT * FROM categories WHERE course_id = ? ORDER BY name", (course_id,)
    ).fetchall()
    breakdown = []
    weighted_points = 0
    active_weight = 0

    for category in categories:
        entries = [
            item for item in graded_items if item["category_id"] == category["id"]
        ]
        if not entries or category["weight"] <= 0:
            continue

        earned = sum(item["score"] for item in entries)
        possible = sum(item["max_score"] for item in entries)
        average = earned / possible * 100 if possible else 0
        weighted_points += average * category["weight"]
        active_weight += category["weight"]
        breakdown.append(
            {
                "name": category["name"],
                "average": average,
                "weight": category["weight"],
            }
        )

    grade = weighted_points / active_weight if active_weight else None
    return grade, breakdown


@app.route("/")
def landing():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/guest", methods=["POST"])
def guest():
    """Create a temporary guest profile."""
    session.clear()
    token = uuid.uuid4().hex
    database = get_db()
    cursor = database.execute(
        """
        INSERT INTO users (username, password_hash, is_guest)
        VALUES (?, ?, 1)
        """,
        (f"guest_{token}", generate_password_hash(token)),
    )
    database.commit()
    session["user_id"] = cursor.lastrowid
    flash("Guest mode started. Create an account later to keep this profile.", "info")
    return redirect(url_for("dashboard"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Create an account or convert the current guest profile."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirmation = request.form.get("confirmation", "")

        if not username:
            flash("Enter a username.", "danger")
        elif len(username) < 3:
            flash("The username must have at least three characters.", "danger")
        elif len(password) < 6:
            flash("The password must have at least six characters.", "danger")
        elif password != confirmation:
            flash("The passwords do not match.", "danger")
        else:
            database = get_db()
            try:
                user = current_user()
                if user and user["is_guest"]:
                    database.execute(
                        """
                        UPDATE users
                        SET username = ?, password_hash = ?, is_guest = 0
                        WHERE id = ?
                        """,
                        (username, generate_password_hash(password), user["id"]),
                    )
                    user_id = user["id"]
                else:
                    cursor = database.execute(
                        """
                        INSERT INTO users (username, password_hash, is_guest)
                        VALUES (?, ?, 0)
                        """,
                        (username, generate_password_hash(password)),
                    )
                    user_id = cursor.lastrowid
                database.commit()
            except sqlite3.IntegrityError:
                flash("That username already exists.", "danger")
            else:
                session.clear()
                session["user_id"] = user_id
                flash("Your account is ready.", "success")
                return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log in to a saved account."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ? AND is_guest = 0", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.", "danger")
        else:
            session.clear()
            session["user_id"] = user["id"]
            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/dashboard")
@login_required
def dashboard():
    """Show progress, grades, and upcoming work."""
    database = get_db()
    courses = database.execute(
        "SELECT * FROM courses WHERE user_id = ? ORDER BY name",
        (session["user_id"],),
    ).fetchall()

    course_cards = []
    for course in courses:
        grade, unused = calculate_course_grade(course["id"], course["grading_mode"])
        course_cards.append({**dict(course), "grade": grade})

    counts = database.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN completed = 0 AND due_date < ? THEN 1 ELSE 0 END) AS overdue
        FROM items
        JOIN courses ON items.course_id = courses.id
        WHERE courses.user_id = ?
        """,
        (date.today().isoformat(), session["user_id"]),
    ).fetchone()

    total = counts["total"] or 0
    completed = counts["completed"] or 0
    progress = round(completed / total * 100) if total else 0
    upcoming = database.execute(
        """
        SELECT items.*, courses.name AS course_name, courses.color AS course_color
        FROM items
        JOIN courses ON items.course_id = courses.id
        WHERE courses.user_id = ?
          AND items.completed = 0
          AND items.due_date IS NOT NULL
          AND items.due_date <= ?
        ORDER BY items.due_date
        LIMIT 8
        """,
        (session["user_id"], (date.today() + timedelta(days=14)).isoformat()),
    ).fetchall()

    return render_template(
        "dashboard.html",
        courses=course_cards,
        total=total,
        completed=completed,
        overdue=counts["overdue"] or 0,
        progress=progress,
        upcoming=upcoming,
        today=date.today().isoformat(),
    )


@app.route("/courses")
@login_required
def courses():
    records = get_db().execute(
        "SELECT * FROM courses WHERE user_id = ? ORDER BY name",
        (session["user_id"],),
    ).fetchall()
    return render_template("courses.html", courses=records)


@app.route("/courses/new", methods=["GET", "POST"])
@login_required
def new_course():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        color = request.form.get("color", "#6c63ff")
        mode = request.form.get("grading_mode", "weighted")
        notes = request.form.get("notes", "").strip()
        if not name or mode not in {"weighted", "points"}:
            flash("Enter a valid course name and grading method.", "danger")
        else:
            database = get_db()
            cursor = database.execute(
                """
                INSERT INTO courses (user_id, name, color, grading_mode, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session["user_id"], name, color, mode, notes),
            )
            database.commit()
            flash("Course created.", "success")
            return redirect(url_for("course_detail", course_id=cursor.lastrowid))
    return render_template("course_form.html", course=None)


@app.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
@login_required
def edit_course(course_id):
    course = owned_course(course_id)
    if course is None:
        return ("Not found", 404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        color = request.form.get("color", "#6c63ff")
        mode = request.form.get("grading_mode", "weighted")
        if not name or mode not in {"weighted", "points"}:
            flash("Enter valid course information.", "danger")
        else:
            database = get_db()
            database.execute(
                "UPDATE courses SET name = ?, color = ?, grading_mode = ? WHERE id = ?",
                (name, color, mode, course_id),
            )
            database.commit()
            flash("Course updated.", "success")
            return redirect(url_for("course_detail", course_id=course_id))
    return render_template("course_form.html", course=course)


@app.route("/courses/<int:course_id>/delete", methods=["POST"])
@login_required
def delete_course(course_id):
    if owned_course(course_id) is None:
        return ("Not found", 404)
    database = get_db()
    database.execute("DELETE FROM courses WHERE id = ?", (course_id,))
    database.commit()
    flash("Course deleted.", "success")
    return redirect(url_for("courses"))


@app.route("/courses/<int:course_id>")
@login_required
def course_detail(course_id):
    course = owned_course(course_id)
    if course is None:
        return ("Not found", 404)
    database = get_db()
    categories = database.execute(
        "SELECT * FROM categories WHERE course_id = ? ORDER BY name", (course_id,)
    ).fetchall()
    items = database.execute(
        """
        SELECT items.*, categories.name AS category_name
        FROM items
        LEFT JOIN categories ON items.category_id = categories.id
        WHERE items.course_id = ?
        ORDER BY items.completed, items.due_date IS NULL, items.due_date, items.title
        """,
        (course_id,),
    ).fetchall()
    grade, breakdown = calculate_course_grade(course_id, course["grading_mode"])
    weight_total = sum(category["weight"] for category in categories)
    return render_template(
        "course.html",
        course=course,
        categories=categories,
        items=items,
        grade=grade,
        breakdown=breakdown,
        weight_total=weight_total,
        today=date.today().isoformat(),
    )


@app.route("/courses/<int:course_id>/notes", methods=["POST"])
@login_required
def save_notes(course_id):
    if owned_course(course_id) is None:
        return ("Not found", 404)
    database = get_db()
    database.execute(
        "UPDATE courses SET notes = ? WHERE id = ?",
        (request.form.get("notes", "").strip(), course_id),
    )
    database.commit()
    flash("Notes saved.", "success")
    return redirect(url_for("course_detail", course_id=course_id))


@app.route("/courses/<int:course_id>/categories", methods=["POST"])
@login_required
def add_category(course_id):
    if owned_course(course_id) is None:
        return ("Not found", 404)
    name = request.form.get("name", "").strip()
    try:
        weight = float(request.form.get("weight", "0"))
    except ValueError:
        weight = -1
    if not name or weight < 0 or weight > 100:
        flash("Enter a category name and a weight from 0 to 100.", "danger")
    else:
        database = get_db()
        try:
            database.execute(
                "INSERT INTO categories (course_id, name, weight) VALUES (?, ?, ?)",
                (course_id, name, weight),
            )
            database.commit()
            flash("Category added.", "success")
        except sqlite3.IntegrityError:
            flash("That category already exists in this course.", "danger")
    return redirect(url_for("course_detail", course_id=course_id))


@app.route("/categories/<int:category_id>/delete", methods=["POST"])
@login_required
def delete_category(category_id):
    database = get_db()
    category = database.execute(
        """
        SELECT categories.*, courses.user_id
        FROM categories
        JOIN courses ON categories.course_id = courses.id
        WHERE categories.id = ?
        """,
        (category_id,),
    ).fetchone()
    if category is None or category["user_id"] != session["user_id"]:
        return ("Not found", 404)
    database.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    database.commit()
    flash("Category deleted. Its activities were kept as uncategorized.", "success")
    return redirect(url_for("course_detail", course_id=category["course_id"]))


def item_form(course_id, item=None):
    """Create or update an activity."""
    course = owned_course(course_id)
    if course is None:
        return ("Not found", 404)
    database = get_db()
    categories = database.execute(
        "SELECT * FROM categories WHERE course_id = ? ORDER BY name", (course_id,)
    ).fetchall()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        due_date = request.form.get("due_date", "").strip() or None
        category_text = request.form.get("category_id", "").strip()
        notes = request.form.get("notes", "").strip()
        completed = 1 if request.form.get("completed") else 0

        if not title:
            flash("Enter an activity title.", "danger")
        else:
            try:
                if due_date:
                    datetime.strptime(due_date, "%Y-%m-%d")
                score, maximum = parse_grade(request.form)
                category_id = int(category_text) if category_text else None
                if category_id and not any(c["id"] == category_id for c in categories):
                    raise ValueError("Select a valid category.")
            except (ValueError, TypeError) as error:
                flash(str(error) or "Enter valid activity information.", "danger")
            else:
                if item is None:
                    database.execute(
                        """
                        INSERT INTO items
                            (course_id, category_id, title, due_date, score,
                             max_score, completed, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            course_id,
                            category_id,
                            title,
                            due_date,
                            score,
                            maximum,
                            completed,
                            notes,
                        ),
                    )
                    message = "Activity added."
                else:
                    database.execute(
                        """
                        UPDATE items
                        SET category_id = ?, title = ?, due_date = ?, score = ?,
                            max_score = ?, completed = ?, notes = ?
                        WHERE id = ?
                        """,
                        (
                            category_id,
                            title,
                            due_date,
                            score,
                            maximum,
                            completed,
                            notes,
                            item["id"],
                        ),
                    )
                    message = "Activity updated."
                database.commit()
                flash(message, "success")
                return redirect(url_for("course_detail", course_id=course_id))

    return render_template(
        "item_form.html", course=course, categories=categories, item=item
    )


@app.route("/courses/<int:course_id>/items/new", methods=["GET", "POST"])
@login_required
def new_item(course_id):
    return item_form(course_id)


@app.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    item = get_db().execute(
        """
        SELECT items.*
        FROM items
        JOIN courses ON items.course_id = courses.id
        WHERE items.id = ? AND courses.user_id = ?
        """,
        (item_id, session["user_id"]),
    ).fetchone()
    if item is None:
        return ("Not found", 404)
    return item_form(item["course_id"], item)


@app.route("/items/<int:item_id>/toggle", methods=["POST"])
@login_required
def toggle_item(item_id):
    database = get_db()
    item = database.execute(
        """
        SELECT items.*
        FROM items
        JOIN courses ON items.course_id = courses.id
        WHERE items.id = ? AND courses.user_id = ?
        """,
        (item_id, session["user_id"]),
    ).fetchone()
    if item is None:
        return ("Not found", 404)
    database.execute(
        "UPDATE items SET completed = ? WHERE id = ?",
        (0 if item["completed"] else 1, item_id),
    )
    database.commit()
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/items/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(item_id):
    database = get_db()
    item = database.execute(
        """
        SELECT items.*
        FROM items
        JOIN courses ON items.course_id = courses.id
        WHERE items.id = ? AND courses.user_id = ?
        """,
        (item_id, session["user_id"]),
    ).fetchone()
    if item is None:
        return ("Not found", 404)
    database.execute("DELETE FROM items WHERE id = ?", (item_id,))
    database.commit()
    flash("Activity deleted.", "success")
    return redirect(url_for("course_detail", course_id=item["course_id"]))


@app.route("/calendar")
@login_required
def calendar_view():
    items = get_db().execute(
        """
        SELECT items.id, items.title, items.due_date, items.completed,
               courses.id AS course_id, courses.name AS course_name,
               courses.color AS course_color
        FROM items
        JOIN courses ON items.course_id = courses.id
        WHERE courses.user_id = ? AND items.due_date IS NOT NULL
        ORDER BY items.due_date
        """,
        (session["user_id"],),
    ).fetchall()
    return render_template("calendar.html", calendar_items=[dict(item) for item in items])


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True)
