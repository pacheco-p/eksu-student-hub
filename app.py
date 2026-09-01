from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)

import os
import uuid
import psycopg2

from psycopg2.extras import RealDictCursor

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


# PostgreSQL connection URL
DATABASE_URL = os.environ.get("DATABASE_URL")


# ==========================================
# UPLOAD CONFIGURATION
# ==========================================

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

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_db():

    if not DATABASE_URL:

        raise RuntimeError(
            "DATABASE_URL environment variable is not configured."
        )

    conn = psycopg2.connect(
        DATABASE_URL
    )

    return conn


# ==========================================
# IMAGE VALIDATION
# ==========================================

def allowed_file(filename):

    return (
        "." in filename
        and
        filename.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_EXTENSIONS
    )
    
# ==========================================
# DATABASE INITIALIZATION
# ==========================================

def init_db():

    conn = get_db()

    cursor = conn.cursor()


    # ======================================
    # USERS TABLE
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (

            id SERIAL PRIMARY KEY,

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS listings (

            id SERIAL PRIMARY KEY,

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

    cursor.execute("""
        ALTER TABLE listings
        ADD COLUMN IF NOT EXISTS image_filename TEXT
    """)


    conn.commit()

    cursor.close()
    conn.close()


# ==========================================
# LOGIN REQUIRED DECORATOR
# ==========================================

def login_required(route_function):

    @wraps(route_function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:

            flash(
                "Please login first."
            )

            return redirect(
                url_for("login")
            )

        return route_function(
            *args,
            **kwargs
        )

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

            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO users
                (
                    full_name,
                    username,
                    email,
                    password
                )

                VALUES (%s, %s, %s, %s)

            """, (
                full_name,
                username,
                email,
                hashed_password
            ))


            conn.commit()

            cursor.close()


        except psycopg2.IntegrityError:

            conn.rollback()

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

        cursor = conn.cursor(
            cursor_factory=RealDictCursor
        )


        cursor.execute("""
            SELECT *

            FROM users

            WHERE username = %s

        """, (
            username,
        ))


        user = cursor.fetchone()


        cursor.close()
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

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )


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
                listings.title ILIKE %s
                OR listings.description ILIKE %s
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
            AND listings.category = %s
        """

        params.append(
            category
        )


    # -------------------------------
    # LOCATION
    # -------------------------------

    if location:

        query += """
            AND listings.location ILIKE %s
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
                AND listings.price >= %s
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
                AND listings.price <= %s
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


    cursor.execute(
        query,
        params
    )


    listings = cursor.fetchall()


    cursor.close()
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

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )


    # Get current user's information

    cursor.execute("""
        SELECT
            id,
            full_name,
            username,
            email,
            created_at

        FROM users

        WHERE id = %s

    """, (
        session["user_id"],
    ))


    user = cursor.fetchone()


    # Get user's listings

    cursor.execute("""
        SELECT *

        FROM listings

        WHERE user_id = %s

        ORDER BY created_at DESC

    """, (
        session["user_id"],
    ))


    listings = cursor.fetchall()


    # Count listings

    cursor.execute("""
        SELECT COUNT(*)

        FROM listings

        WHERE user_id = %s

    """, (
        session["user_id"],
    ))


    listing_count = cursor.fetchone()["count"]


    cursor.close()
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


            original_name = secure_filename(
                image.filename
            )


            extension = (
                original_name
                .rsplit(".", 1)[1]
                .lower()
            )


            image_filename = (
                f"{uuid.uuid4().hex}."
                f"{extension}"
            )


            image_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                image_filename
            )


            image.save(
                image_path
            )


        # ==================================
        # SAVE LISTING
        # ==================================

        conn = get_db()

        cursor = conn.cursor()


        cursor.execute("""
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

            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )

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

        cursor.close()
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

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )


    cursor.execute("""
        SELECT *

        FROM listings

        WHERE id = %s

        AND user_id = %s

    """, (
        listing_id,
        session["user_id"]
    ))


    listing = cursor.fetchone()


    # --------------------------------------
    # SECURITY CHECK
    # --------------------------------------

    if listing is None:

        cursor.close()
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

            cursor.close()
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

            cursor.close()
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

                cursor.close()
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


            image.save(
                image_path
            )


            # Delete old image

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

        cursor.execute("""
            UPDATE listings

            SET
                title = %s,
                category = %s,
                price = %s,
                location = %s,
                description = %s,
                image_filename = %s

            WHERE id = %s

            AND user_id = %s

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

        cursor.close()
        conn.close()


        flash(
            "Listing updated successfully."
        )


        return redirect(
            url_for("dashboard")
        )


    cursor.close()
    conn.close()


    return render_template(
        "edit_listing.html",
        listing=listing
    )


# ==========================================
# SELLER PROFILE
# ==========================================

@app.route(
    "/profile/<username>"
)
def seller_profile(username):

    conn = get_db()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )


    # Get seller

    cursor.execute("""
        SELECT
            id,
            full_name,
            username,
            email,
            created_at

        FROM users

        WHERE username = %s

    """, (
        username,
    ))


    user = cursor.fetchone()


    if user is None:

        cursor.close()
        conn.close()

        return (
            "Seller not found",
            404
        )


    # Get seller listings

    cursor.execute("""
        SELECT *

        FROM listings

        WHERE user_id = %s

        ORDER BY created_at DESC

    """, (
        user["id"],
    ))


    listings = cursor.fetchall()


    cursor.close()
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

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )


    cursor.execute("""
        SELECT

            listings.*,

            users.full_name,

            users.username,

            users.email

        FROM listings

        JOIN users

        ON listings.user_id = users.id

        WHERE listings.id = %s

    """, (
        listing_id,
    ))


    listing = cursor.fetchone()


    cursor.close()
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

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )


    # Only retrieve owned listing

    cursor.execute("""
        SELECT *

        FROM listings

        WHERE id = %s

        AND user_id = %s

    """, (
        listing_id,
        session["user_id"]
    ))


    listing = cursor.fetchone()


    if listing is None:

        cursor.close()
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

    cursor.execute("""
        DELETE FROM listings

        WHERE id = %s

        AND user_id = %s

    """, (
        listing_id,
        session["user_id"]
    ))


    conn.commit()

    cursor.close()
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