from flask import Flask, jsonify, render_template, url_for, flash, redirect, request
from stockstash import app, mongo, bcrypt, mail
from stockstash.models import User, Portfolio, Watchlist
from stockstash.forms import (RegistrationForm, LoginForm, AddStockForm, AddStockFormWatchlist, 
                                AccountForm, RequestResetForm, ResetPasswordForm)
from flask_login import login_user, current_user, logout_user, login_required
from stockstash.data.stockreader import get_stock_data, get_most_recent_business_day
from flask_mail import Message


@app.route("/")
def index():
    return render_template('home.html', title='Stockstash')

# login route
@app.route("/login", methods=['GET', 'POST'])
def login():
    # if current user is logged in, then redirect
    if current_user.is_authenticated:
        return redirect(url_for('portfolio'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.objects.get(username=form.username.data)
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            return redirect(url_for('portfolio'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)

# account route
@app.route('/account', methods=['GET','POST'])
@login_required
def account():
    form = AccountForm()

    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.fname = form.fname.data
        current_user.lname = form.lname.data
        current_user.brokerage = form.brokerage.data
        current_user.save()
        flash(f'Updated Account!', 'success')
        return redirect(url_for('account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.fname.data = current_user.fname
        form.lname.data = current_user.lname
        form.brokerage.data = current_user.brokerage
    return render_template('account.html', title='Account', form=form)

# register route
@app.route('/register', methods=['GET','POST'])
def register():
    # if current user is logged in, then redirect
    if current_user.is_authenticated:
        return redirect(url_for('portfolio'))
    # create the registration form object
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_pass = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data,password=hashed_pass,
                    fname=form.fname.data, lname=form.lname.data,
                    brokerage=form.brokerage.data, portfolio=[], watchlist=[])
        user.save()
        flash(f'Welcome to StockStash {form.fname.data}! '
              f'\nPlease login with your new account.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)


# logout route
@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('login'))

# portfolio
@app.route('/portfolio', methods=['GET', 'POST'])
@login_required
def portfolio():

    # Get the stock data from the current users portfolio
    tickers = []
    user = User.objects.get(username=current_user['username'])
    for stock in user['portfolio']:
        tickers.append(stock['ticker'])

    date = get_most_recent_business_day()
    stockdata = (get_stock_data(tickers, date, date))
    
    # Form to add stocks to portfolio
    form = AddStockForm()
    user = User.objects.get(username=current_user['username'])
    if form.validate_on_submit():
        new_stock = Portfolio(ticker=form.ticker.data, price=form.price.data)
        user = User.objects.get(username=current_user['username'])
        user.portfolio.append(new_stock)
        user.save()
        flash(f'New stock added!', 'success')
        return redirect(url_for('portfolio'))

    return render_template('portfolio.html', title='Portfolio', data=stockdata, form=form)

# watchlist
@app.route('/watchlist', methods=['GET', 'POST'])
@login_required
def watchlist():

    # Get the stock data from api
    tickers = []
    user = User.objects.get(username=current_user['username'])
    for stock in user['watchlist']:
        tickers.append(stock['ticker'])
    date = get_most_recent_business_day()
    apidata = (get_stock_data(tickers, date, date))

    # Get the stock data from database
    dbdata = {}
    for stock in user['watchlist']:
        dbdata[stock['ticker']] = {
            'High Price': float(stock['highprice']),
            'Low Price': float(stock['lowprice'])
        }

    # Form to add stocks to portfolio
    form = AddStockFormWatchlist()
    user = User.objects.get(username=current_user['username'])
    if form.validate_on_submit():
        new_stock = Watchlist(ticker=form.ticker.data, lowprice=form.lowprice.data, highprice=form.highprice.data)
        user = User.objects.get(username=current_user['username'])
        user.watchlist.append(new_stock)
        user.save()
        flash(f'New stock added!', 'success')
        return redirect(url_for('watchlist'))

    return render_template('watchlist.html', title='Watchlist', apidata=apidata,  dbdata=dbdata, form=form)

# delete from portfolio
@app.route("/portfolio/<string:ticker_id>/delete", methods=['POST'])
@login_required
def delete_portfolio_ticker(ticker_id):
    user = User.objects(username=current_user['username'])
    user.update_one(pull__portfolio__ticker = Portfolio(ticker=ticker_id).ticker)
    flash(ticker_id + ' has been deleted from your portfolio', 'success')
    return redirect(url_for('portfolio'))

# delete from watchlist
@app.route("/watchlist/<string:ticker_id>/delete", methods=['POST'])
@login_required
def delete_watchlist_ticker(ticker_id):
    user = User.objects(username=current_user['username'])
    user.update_one(pull__watchlist__ticker = Watchlist(ticker=ticker_id).ticker)
    flash(ticker_id + ' has been deleted from your watchlist', 'success')
    return redirect(url_for('watchlist'))

# delete user
@app.route("/admin/<string:username>/delete", methods=['POST'])
@login_required
def delete_user(username):
    user = User.objects(username=username)
    # logout and delete if current user is deleting self
    if username == current_user['username']:
        logout_user()
        flash( username + ' has been deleted from the system.  Admin is no longer active', 'success')
        user.delete()
        return redirect('login')
    user.delete()
    flash( username + ' has been deleted from the system', 'success')
    return redirect(url_for('admin_panel'))

# assign admin role
@app.route("/admin/<string:username>/assign", methods=['POST'])
@login_required
def assign_admin(username):
    user = User.objects(username=username)
    user.update_one(set__admin = True)
    flash( username + ' has been assigned admin privledges', 'success')
    return redirect(url_for('admin_panel'))

# remove admin role
@app.route("/admin/<string:username>/remove", methods=['POST'])
@login_required
def remove_admin(username):
    redirect_url = 'admin_panel'

    # logout user if removing admin privledges and set redirect to login
    if username == current_user['username']:
        logout_user()
        redirect_url = 'login'
    user = User.objects(username=username)
    user.update_one(set__admin = False)
    flash( username + ' admin privledges removed', 'success')
    return redirect(url_for(redirect_url))

# admin_panel
@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_panel():
    #user count
    users = User.objects
    num_users = users.count()

    json_users = users.to_json()
    return render_template('admin.html', title='Admin Panel', data=users)

def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('stockstash - Password Reset Request', 
                    sender='stockstash.info@gmail.com', 
                    recipients=[user.username])
    msg.body = f'''To reset your password, visit the following link:
{url_for('reset_token', token=token, _external=True)}

If you did not make this request then simply ignore this email and no changes will be made.
'''
    mail.send(msg)


# request to reset password
@app.route('/reset_password', methods=['GET','POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('portfolio'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.objects.get(username=form.username.data)
        send_reset_email(user)
        flash('An email has been sent with instructions to reset your password.', 'info')
        return redirect(url_for('login'))
    return render_template('reset_request.html', title='Reset Password', form=form)

# reset password
@app.route('/reset_password/<token>', methods=['GET','POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('portfolio'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_pass = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_pass
        user.save()
        flash('Your password has been updated! You are now able to log in.', 'info')
        return redirect(url_for('login'))
    return render_template('reset_token.html', title='Reset Password', form=form)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)