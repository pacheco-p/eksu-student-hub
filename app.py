from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)

import sqlite3
import os
import uuid

from dotenv import load_dotenv

from functools import wraps

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename


# ==========================================
# APP CONFIGURATION
# ==========================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "dev-secret-key"
)

DATABASE = "database.db"

UPLOAD_FOLDER = "static/uploads"

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Maximum upload size = 5MB
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


# Make sure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_db():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn


# ==========================================
# IMAGE VALIDATION
# ==========================================

def allowed_file(filename):

    return (
        "." in filename
        and
        filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

def init_db():

    conn = get_db()


    # ======================================
    # USERS TABLE
    # ======================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            full_name TEXT NOT NULL,

            username TEXT UNIQUE NOT NULL,

            email TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL,

            created_at TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP

        )
    """)


    # ======================================
    # LISTINGS TABLE
    # ======================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS listings (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            title TEXT NOT NULL,

            category TEXT NOT NULL,

            price REAL NOT NULL,

            location TEXT NOT NULL,

            description TEXT NOT NULL,

            image_url TEXT,

            image_filename TEXT,

            created_at TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
            REFERENCES users(id)

        )
    """)


    # ======================================
    # DATABASE MIGRATION
    # ======================================
    #
    # Your existing database already has
    # the listings table without image_filename.
    #
    # This safely adds the new column.
    #

    try:

        conn.execute("""
            ALTER TABLE listings
            ADD COLUMN image_filename TEXT
        """)

    except sqlite3.OperationalError:

        # Column already exists.
        pass


    conn.commit()

    conn.close()


# ==========================================
# LOGIN REQUIRED DECORATOR
# ==========================================

def login_required(route_function):

    @wraps(route_function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:

            flash("Please login first.")

            return redirect(
                url_for("login")
            )

        return route_function(*args, **kwargs)

    return wrapper


# ==========================================
# HOME
# ==========================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# ==========================================
# REGISTER
# ==========================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        full_name = request.form[
            "full_name"
        ].strip()

        username = request.form[
            "username"
        ].strip()

        email = request.form[
            "email"
        ].strip().lower()

        password = request.form[
            "password"
        ]


        # -------------------------------
        # VALIDATION
        # -------------------------------

        if (
            not full_name
            or not username
            or not email
            or not password
        ):

            flash(
                "Please fill in all fields."
            )

            return redirect(
                url_for("register")
            )


        # -------------------------------
        # HASH PASSWORD
        # -------------------------------

        hashed_password = (
            generate_password_hash(
                password
            )
        )


        conn = get_db()


        try:

            conn.execute("""
                INSERT INTO users
                (
                    full_name,
                    username,
                    email,
                    password
                )

                VALUES (?, ?, ?, ?)

            """, (
                full_name,
                username,
                email,
                hashed_password
            ))


            conn.commit()


        except sqlite3.IntegrityError:

            conn.close()

            flash(
                "Username or email already exists."
            )

            return redirect(
                url_for("register")
            )


        conn.close()


        flash(
            "Account created successfully."
        )


        return redirect(
            url_for("login")
        )


    return render_template(
        "register.html"
    )


# ==========================================
# LOGIN
# ==========================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        username = request.form[
            "username"
        ].strip()

        password = request.form[
            "password"
        ]


        conn = get_db()


        user = conn.execute("""
            SELECT *

            FROM users

            WHERE username = ?

        """, (
            username,
        )).fetchone()


        conn.close()


        # -------------------------------
        # CHECK LOGIN
        # -------------------------------

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]

            session["username"] = (
                user["username"]
            )

            session["full_name"] = (
                user["full_name"]
            )


            return redirect(
                url_for("home")
            )


        flash(
            "Invalid username or password."
        )


    return render_template(
        "login.html"
    )


# ==========================================
# LOGOUT
# ==========================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )


# ==========================================
# MARKETPLACE
# ==========================================

@app.route("/marketplace")
def marketplace():

    search = request.args.get(
        "search",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    location = request.args.get(
        "location",
        ""
    ).strip()

    min_price = request.args.get(
        "min_price",
        ""
    ).strip()

    max_price = request.args.get(
        "max_price",
        ""
    ).strip()


    conn = get_db()


    query = """
        SELECT

            listings.*,

            users.full_name,

            users.username

        FROM listings

        JOIN users

        ON listings.user_id = users.id

        WHERE 1=1
    """


    params = []


    # -------------------------------
    # SEARCH
    # -------------------------------

    if search:

        query += """
            AND (
                listings.title LIKE ?
                OR listings.description LIKE ?
            )
        """

        search_term = f"%{search}%"


        params.extend([
            search_term,
            search_term
        ])


    # -------------------------------
    # CATEGORY
    # -------------------------------

    if category:

        query += """
            AND listings.category = ?
        """

        params.append(category)


    # -------------------------------
    # LOCATION
    # -------------------------------

    if location:

        query += """
            AND listings.location LIKE ?
        """

        params.append(
            f"%{location}%"
        )


    # -------------------------------
    # MINIMUM PRICE
    # -------------------------------

    if min_price:

        try:

            query += """
                AND listings.price >= ?
            """

            params.append(
                float(min_price)
            )

        except ValueError:

            pass


    # -------------------------------
    # MAXIMUM PRICE
    # -------------------------------

    if max_price:

        try:

            query += """
                AND listings.price <= ?
            """

            params.append(
                float(max_price)
            )

        except ValueError:

            pass


    # -------------------------------
    # SORT
    # -------------------------------

    query += """
        ORDER BY listings.created_at DESC
    """


    listings = conn.execute(
        query,
        params
    ).fetchall()


    conn.close()


    return render_template(
        "marketplace.html",

        listings=listings,

        search=search,

        category=category,

        location=location,

        min_price=min_price,

        max_price=max_price
    )


# ==========================================
# USER DASHBOARD
# ==========================================

@app.route("/dashboard")
@login_required
def dashboard():

    conn = get_db()

    # Get current user's information
    user = conn.execute("""
        SELECT
            id,
            full_name,
            username,
            email,
            created_at
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    )).fetchone()


    # Get all listings belonging to the user
    listings = conn.execute("""
        SELECT *
        FROM listings
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (
        session["user_id"],
    )).fetchall()


    # Count user's listings
    listing_count = conn.execute("""
        SELECT COUNT(*)
        FROM listings
        WHERE user_id = ?
    """, (
        session["user_id"],
    )).fetchone()[0]


    conn.close()


    return render_template(
        "dashboard.html",

        user=user,

        listings=listings,

        listing_count=listing_count
    )

# ==========================================
# CREATE LISTING
# ==========================================

@app.route(
    "/create-listing",
    methods=["GET", "POST"]
)
@login_required
def create_listing():

    if request.method == "POST":

        title = request.form[
            "title"
        ].strip()

        category = request.form[
            "category"
        ]

        price = request.form[
            "price"
        ]

        location = request.form[
            "location"
        ].strip()

        description = request.form[
            "description"
        ].strip()


        # ==================================
        # VALIDATE TEXT FIELDS
        # ==================================

        if (
            not title
            or not category
            or not price
            or not location
            or not description
        ):

            flash(
                "Please fill in all required fields."
            )

            return redirect(
                url_for("create_listing")
            )


        # ==================================
        # VALIDATE PRICE
        # ==================================

        try:

            price_value = float(price)

            if price_value < 0:

                raise ValueError

        except ValueError:

            flash(
                "Please enter a valid price."
            )

            return redirect(
                url_for("create_listing")
            )


        # ==================================
        # IMAGE UPLOAD
        # ==================================

        image = request.files.get(
            "image"
        )

        image_filename = None


        if image and image.filename:

            # Check file extension

            if not allowed_file(
                image.filename
            ):

                flash(
                    "Invalid image format. "
                    "Use JPG, JPEG, PNG or WEBP."
                )

                return redirect(
                    url_for("create_listing")
                )


            # Secure original filename

            original_name = secure_filename(
                image.filename
            )


            # Get extension

            extension = (
                original_name
                .rsplit(".", 1)[1]
                .lower()
            )


            # Generate unique filename

            image_filename = (
                f"{uuid.uuid4().hex}."
                f"{extension}"
            )


            # Final save path

            image_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                image_filename
            )


            # Save image

            image.save(
                image_path
            )


        # ==================================
        # SAVE LISTING
        # ==================================

        conn = get_db()


        conn.execute("""
            INSERT INTO listings
            (
                user_id,
                title,
                category,
                price,
                location,
                description,
                image_filename
            )

            VALUES (?, ?, ?, ?, ?, ?, ?)

        """, (
            session["user_id"],
            title,
            category,
            price_value,
            location,
            description,
            image_filename
        ))


        conn.commit()

        conn.close()


        flash(
            "Your listing has been published!"
        )


        return redirect(
            url_for("marketplace")
        )


    return render_template(
        "create_listing.html"
    )


# ==========================================
# EDIT LISTING
# ==========================================

@app.route(
    "/listing/<int:listing_id>/edit",
    methods=["GET", "POST"]
)
@login_required
def edit_listing(listing_id):

    conn = get_db()


    # Get listing belonging to current user
    listing = conn.execute("""
        SELECT *
        FROM listings
        WHERE id = ?
        AND user_id = ?
    """, (
        listing_id,
        session["user_id"]
    )).fetchone()


    # --------------------------------------
    # SECURITY CHECK
    # --------------------------------------

    if listing is None:

        conn.close()

        flash(
            "You cannot edit this listing."
        )

        return redirect(
            url_for("dashboard")
        )


    # --------------------------------------
    # UPDATE LISTING
    # --------------------------------------

    if request.method == "POST":

        title = request.form[
            "title"
        ].strip()

        category = request.form[
            "category"
        ]

        price = request.form[
            "price"
        ]

        location = request.form[
            "location"
        ].strip()

        description = request.form[
            "description"
        ].strip()


        # -------------------------------
        # VALIDATION
        # -------------------------------

        if (
            not title
            or not category
            or not price
            or not location
            or not description
        ):

            flash(
                "Please fill in all required fields."
            )

            conn.close()

            return redirect(
                url_for(
                    "edit_listing",
                    listing_id=listing_id
                )
            )


        try:

            price_value = float(price)

            if price_value < 0:

                raise ValueError

        except ValueError:

            flash(
                "Please enter a valid price."
            )

            conn.close()

            return redirect(
                url_for(
                    "edit_listing",
                    listing_id=listing_id
                )
            )


        # -------------------------------
        # IMAGE
        # -------------------------------

        image = request.files.get(
            "image"
        )

        image_filename = listing[
            "image_filename"
        ]


        if image and image.filename:

            if not allowed_file(
                image.filename
            ):

                flash(
                    "Invalid image format. "
                    "Use JPG, JPEG, PNG or WEBP."
                )

                conn.close()

                return redirect(
                    url_for(
                        "edit_listing",
                        listing_id=listing_id
                    )
                )


            original_name = secure_filename(
                image.filename
            )


            extension = (
                original_name
                .rsplit(".", 1)[1]
                .lower()
            )


            new_filename = (
                f"{uuid.uuid4().hex}."
                f"{extension}"
            )


            image_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                new_filename
            )


            image.save(image_path)


            # Delete old uploaded image
            # if one exists.

            old_filename = listing[
                "image_filename"
            ]


            if old_filename:

                old_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    old_filename
                )


                if os.path.exists(old_path):

                    try:

                        os.remove(old_path)

                    except OSError:

                        pass


            image_filename = new_filename


        # -------------------------------
        # UPDATE DATABASE
        # -------------------------------

        conn.execute("""
            UPDATE listings

            SET
                title = ?,
                category = ?,
                price = ?,
                location = ?,
                description = ?,
                image_filename = ?

            WHERE id = ?
            AND user_id = ?

        """, (
            title,
            category,
            price_value,
            location,
            description,
            image_filename,
            listing_id,
            session["user_id"]
        ))


        conn.commit()

        conn.close()


        flash(
            "Listing updated successfully."
        )


        return redirect(
            url_for("dashboard")
        )


    conn.close()


    return render_template(
        "edit_listing.html",
        listing=listing
    )

# ==========================================
# SELLER PROFILE
# ==========================================

@app.route("/profile/<username>")
def seller_profile(username):

    conn = get_db()

    # Get seller
    user = conn.execute("""
        SELECT
            id,
            full_name,
            username,
            email,
            created_at
        FROM users
        WHERE username = ?
    """, (
        username,
    )).fetchone()


    # Seller doesn't exist
    if user is None:

        conn.close()

        return (
            "Seller not found",
            404
        )


    # Get seller's listings
    listings = conn.execute("""
        SELECT *
        FROM listings
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (
        user["id"],
    )).fetchall()


    conn.close()


    return render_template(
        "profile.html",

        user=user,

        listings=listings
    )

# ==========================================
# VIEW LISTING
# ==========================================

@app.route(
    "/listing/<int:listing_id>"
)
def view_listing(listing_id):

    conn = get_db()


    listing = conn.execute("""
        SELECT

            listings.*,

            users.full_name,

            users.username,

            users.email

        FROM listings

        JOIN users

        ON listings.user_id = users.id

        WHERE listings.id = ?

    """, (
        listing_id,
    )).fetchone()


    conn.close()


    if listing is None:

        return (
            "Listing not found",
            404
        )


    return render_template(
        "listing.html",

        listing=listing
    )
    
    
# ==========================================
# DELETE LISTING
# ==========================================

@app.route(
    "/listing/<int:listing_id>/delete",
    methods=["POST"]
)
@login_required
def delete_listing(listing_id):

    conn = get_db()


    # Only retrieve listing owned
    # by the logged-in user.

    listing = conn.execute("""
        SELECT *
        FROM listings
        WHERE id = ?
        AND user_id = ?
    """, (
        listing_id,
        session["user_id"]
    )).fetchone()


    if listing is None:

        conn.close()

        flash(
            "You cannot delete this listing."
        )

        return redirect(
            url_for("dashboard")
        )


    # --------------------------------------
    # DELETE IMAGE
    # --------------------------------------

    if listing["image_filename"]:

        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            listing["image_filename"]
        )


        if os.path.exists(image_path):

            try:

                os.remove(image_path)

            except OSError:

                pass


    # --------------------------------------
    # DELETE DATABASE RECORD
    # --------------------------------------

    conn.execute("""
        DELETE FROM listings

        WHERE id = ?
        AND user_id = ?

    """, (
        listing_id,
        session["user_id"]
    ))


    conn.commit()

    conn.close()


    flash(
        "Listing deleted successfully."
    )


    return redirect(
        url_for("dashboard")
    )


# ==========================================
# START APPLICATION
# ==========================================

if __name__ == "__main__":

    init_db()

    app.run(
        debug=False
    )