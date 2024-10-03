import os, smtplib
from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from hashlib import sha256
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm, ContactForm

MY_EMAIL = os.environ.get("MY_EMAIL")
EMAIL_PASSWD = os.environ.get("MY_EMAIL_PASSWD")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("FLASK_SECRET_KEY")
ckeditor = CKEditor(app)
Bootstrap5(app)

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)

# CREATE DATABASE
class Base(DeclarativeBase):
    pass

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author: Mapped["User"] = relationship(back_populates="posts")
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    comments: Mapped[list["Comment"]] = relationship(back_populates='parent_post')


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(250))
    name: Mapped[str] = mapped_column(String(100))
    posts: Mapped[list["BlogPost"]] = relationship(back_populates='author')
    comments: Mapped[list["Comment"]] = relationship(back_populates='comment_author')


class Comment(db.Model):
    __tablename__ = 'comments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comment_author: Mapped["User"] = relationship(back_populates="comments")
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    post_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("blog_posts.id"))
    parent_post: Mapped["BlogPost"] = relationship(back_populates="comments")


with app.app_context():
    db.create_all()


# Flask-gravatar is not compatible with Flask 3.x, so had to implement custom function instead
def gravatar_url(email, size=100, rating='g', default='retro', force_default=False):
    hash_value = sha256(email.lower().encode('utf-8')).hexdigest()
    return f"https://www.gravatar.com/avatar/{hash_value}?s={size}&d={default}&r={rating}&f={force_default}"


# Create send email function for Contact form
def send_email(name, email, message):
    email_message = f"Subject:New Message from Contact Form\n\nName: {name}\nEmail: {email}\nMessage: {message}"
    with smtplib.SMTP("smtp.gmail.com", port=587) as connection:
        connection.starttls()
        connection.login(MY_EMAIL, EMAIL_PASSWD)
        connection.sendmail(MY_EMAIL, MY_EMAIL, email_message)


#Create admin-only decorator
def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and current_user.id == 1:
            return f(*args, **kwargs)
        else:
            return abort(403)
        
    return decorated_function


@app.route('/register', methods=['GET', 'POST'])
def register():
    register_form = RegisterForm()
    if register_form.validate_on_submit():
        email = register_form.email.data
        result = db.session.execute(db.select(User).where(User.email == email))
        # Note, email in db is unique so will only have one result.
        user = result.scalar()
        if user:
        # User already exists
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))
        else:
            hashed_password = generate_password_hash(
                password=register_form.password.data,
                method="scrypt",
                salt_length=16
            )
            new_user = User(
                email=register_form.email.data,
                name=register_form.name.data,
                password=hashed_password
            )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for('get_all_posts'))

    return render_template("register.html", form=register_form)


@app.route('/login', methods=["GET", "POST"])
def login():
    login_form = LoginForm()
    if login_form.validate_on_submit():
        password=login_form.password.data
        # Find user by email entered.
        result = db.session.execute(db.select(User).where(User.email == login_form.email.data))
        user = result.scalar()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('get_all_posts'))
        else:
            flash("Invalid credentials, please try again.")
            return redirect(url_for('login'))

    return render_template("login.html", form=login_form)



@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    comment_form = CommentForm()
    # Only allow logged-in users to comment on posts
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register to comment.")
            return redirect(url_for("login"))

        new_comment = Comment(
            text=comment_form.comment_text.data,
            comment_author=current_user,
            parent_post=requested_post
        )
        db.session.add(new_comment)
        db.session.commit()
        
    return render_template("post.html", post=requested_post, current_user=current_user, form=comment_form, gravatar_url=gravatar_url) 


@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, current_user=current_user)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, current_user=current_user)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=['GET', 'POST'])
def contact():
    contact_form = ContactForm()
    if contact_form.validate_on_submit():
        send_email(name=contact_form.name.data, email=contact_form.email.data, message=contact_form.message.data)
        return render_template("contact.html", msg_sent=True, form=contact_form)
    return render_template("contact.html", msg_sent=False, form=contact_form)


if __name__ == "__main__":
    app.run(port=5002)
