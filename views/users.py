from main import app, db, mail, login_manager
from views import Form
from models.user import User, PasswordReset

from sqlalchemy.exc import IntegrityError

from flask import (
    render_template, redirect, request, flash,
    url_for, _request_ctx_stack
)
from flask.ext.login import (
    login_user, login_required, logout_user, current_user,
)
from flask.ext.mail import Message

from wtforms.validators import Required, Email, EqualTo, ValidationError
from wtforms import TextField, PasswordField, HiddenField

import re

import pprint

login_manager.setup_app(app, add_context_processor=True)
app.login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(userid):
    user = User.query.filter_by(id=userid).first()
    _request_ctx_stack.top.badgeid = user.badgeid
    return user


class NextURLField(HiddenField):
    def _value(self):
        # Cheap way of ensuring we don't get absolute URLs
        if not self.data or '//' in self.data:
            return ''
        if not re.match('^[-_0-9a-zA-Z/?=&]+$', self.data):
            app.logger.error("Dropping next URL %s", repr(self.data))
            return ''
        return self.data

class LoginForm(Form):
    email = TextField('Email', [Email(), Required()])
    password = PasswordField('Password', [Required()])
    next = NextURLField('Next')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated():
        return redirect('/home')

    form = LoginForm(request.form, next=request.args.get('next'))
    if request.method == 'POST' and form.validate():

        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect('/home')
        else:
            flash("Invalid login details!")

    return render_template("login.html", form=form)


class SignupForm(Form):
    badgeid = TextField('Badge ID', [Required()])
    password = PasswordField('Password', [Required(), EqualTo('confirm', message="Passwords do not match")])
    confirm = PasswordField('Confirm password', [Required()])
    email = TextField('Email', [Email()])
    next = NextURLField('Next')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated():
        return redirect('/home')

    form = SignupForm(request.form)

    if form.email.data:
        user = User(form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        login_user(user)

        return redirect('/home')

    return render_template('signup.html', form=form)


class ForgotPasswordForm(Form):
    email = TextField('Email', [Email(), Required()])

    def validate_email(form, field):
        user = User.query.filter_by(email=form.email.data).first()
        if not user:
            raise ValidationError("Email address not found")
        form._user = user

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm(request.form)

    if form.validate_on_submit():
        if form._user:
            reset = PasswordReset(form.email.data)
            reset.new_token()
            db.session.add(reset)
            db.session.commit()

            msg = Message("EMF password reset",
                sender=app.config['SCHEDULE_EMAIL'],
                recipients=[form.email.data])
            msg.body = render_template('reset-password-email.txt', user=form._user, reset=reset)
            mail.send(msg)

        return redirect(url_for('reset_password', email=form.email.data))

    return render_template('forgot-password.html', form=form)


class ResetPasswordForm(Form):
    email = TextField('Email', [Email(), Required()])
    token = TextField('Token', [Required()])
    password = PasswordField('New password', [Required(), EqualTo('confirm', message="Passwords do not match")])
    confirm = PasswordField('Confirm password', [Required()])

    def validate_token(form, field):
        reset = PasswordReset.query.filter_by(email=form.email.data, token=field.data).first()
        if not reset:
            raise ValidationError("Token not found")
        if reset.expired():
            raise ValidationError("Token has expired")
        form._reset = reset

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    form = ResetPasswordForm(request.form, email=request.args.get('email'), token=request.args.get('token'))

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        db.session.delete(form._reset)
        user.set_password(form.password.data)
        db.session.commit()

        return redirect("/")

    return render_template('reset-password.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main'))


