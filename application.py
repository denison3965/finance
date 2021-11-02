import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show actions of stocks"""

    #Getting user
    username = db.execute("SELECT username FROM users WHERE id = :uid", uid=int(session['user_id']))[0]["username"]

    stocks = db.execute("SELECT nameStock, quantity FROM actions WHERE username = :username", username=username)

    # get user cash total
    result = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
    user_cash = result[0]['cash']


    if not stocks:
         return render_template("index.html")

    grand_total = user_cash

    # List to add all totals
    total_sum = []

    # determine current price, stock total value and grand total value
    for stock in stocks:
        symbol = str(stock["nameStock"])
        shares = int(stock["quantity"])
        name = lookup(symbol)["name"]
        price = lookup(symbol)["price"]
        total = shares * price
        stock["name"] = name
        stock["price"] = price
        stock["total"] = total
        total_sum.append(float(total))

    cash_available = db.execute("SELECT cash FROM users WHERE username = :username", username=username)[0]["cash"]
    cash_total = sum(total_sum) + cash_available

    return render_template("index.html", stocks=stocks, cash=cash_available, total=cash_total)



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """buy symbol"""
    if request.method == "POST":
 # Store the dictionary returned from the search in a variable
        look = lookup(request.form.get("symbol"))

        # Store the shares inputed
        shares = request.form.get("shares")

        # If the symbol searched or number of shares is invalid, return apology
        if look == None:
            return apology("invalid symbol", 400)
        elif not shares.isdigit() or int(shares) < 1:
            return apology("share must be at least 1", 400)

        # Store how much money the user has
        cash = db.execute("SELECT cash FROM users WHERE id = :uid", uid=int(session['user_id']))

        # Store the value of purchase
        value = look["price"] * int(shares)

        # If the user don't have enough money, apologize
        if int(cash[0]["cash"]) < value:
            return apology("You don't have enough money to proceed", 403)

        # If the user can afford the purchase, proceed
        else:
            # Subtract the value of purchase from the user's cash
            db.execute("UPDATE users SET cash = cash - :value WHERE id = :uid", value=value, uid=int(session['user_id']))

            # Add the transaction to the user's history
            db.execute("INSERT INTO history_bought (username, operation, symbol, price, shares) VALUES (:username, 'BUY', :symbol, :price, :shares)",
            username=db.execute("SELECT username FROM users WHERE id = :uid", uid=int(session['user_id']))[0]["username"],
            symbol=look['symbol'], price=look['price'], shares=request.form.get('shares'))

            # Add the stock to the user's portfolio
            db.execute("INSERT INTO actions (username, nameStock, quantity) VALUES (:username, :symbol, :shares)",
            username=db.execute("SELECT username FROM users WHERE id = :uid", uid=int(session['user_id']))[0]["username"],
            symbol=look['symbol'], shares=request.form.get('shares'))

            # Send them to the portfolio
            return redirect("/")

    else:
        return render_template('buy.html')


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
      # Store the username of the user logged
    username = db.execute("SELECT username FROM users WHERE id = :uid", uid=int(session['user_id']))[0]["username"]

    # Put information from 'history' into a list
    stocks = db.execute("SELECT operation, symbol, price, date, time, shares FROM history_bought WHERE username = :username", username=username)

    # Iterate over the stocks list to append the faulty information needed in history.html table
    for stock in stocks:
        symbol = str(stock["symbol"])
        name = lookup(symbol)["name"]
        stock["name"] = name

    return render_template("history.html", stocks=stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""

    # Define username as the input in the form
    username = request.args.get('username')

    # Identify if that input is in the database
    other_username = db.execute("SELECT username FROM users WHERE username = :username", username=username)

    # If the username is in database, return false, if not return true and proceed
    try:
        result = other_username[0]['username']
        if not result:
            return jsonify(True)
        else:
            return jsonify(False)
    except IndexError:
        return jsonify(True)


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":

        # Getting the informations about symbol passed through the service API
        look = lookup(request.form.get("symbol"))

        if look == None:
            return apology("invalid symbol", 400)

        # Retun the information aboute symbol
        else:
            return render_template("quote_action.html", name=look["name"], symbol=look["symbol"], price=usd(look["price"]))

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        if not request.form.get('username'):
             return apology("must provide username to register", 400)

        if not request.form.get('password'):
            return apology("must provide password to register", 400)

        if not request.form.get('confirmation'):
            return apology("must provide password Confirm to register", 400)

        if request.form.get('password') != request.form.get('confirmation'):
            return apology("the password Confirm is not equal the password")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))


        if len(rows) > 0:
            return apology("this nameuser already exist in database, choice other", 400);


        result = db.execute("INSERT INTO users (username, hash) VALUES (?,?)", request.form.get('username'), generate_password_hash(request.form.get('password')))

        # Ensure username is not repeated
        if not result:
            return apology("this nameuser already exist in database, choice other", 400)


        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"));

        session["user_id"] = rows[0]["id"]

        return redirect("/")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Getting the username
    username = db.execute("SELECT username FROM users WHERE id = :uid", uid=int(session['user_id']))[0]["username"]

    if request.method == "POST":
        # Getting the actions
        look = lookup(request.form.get("symbol"))

        # Getting the shares
        shares = request.form.get("shares")

        # Store the number of shares the user has
        user_shares = db.execute("SELECT quantity FROM actions WHERE username = :username and nameStock = :nameStock",
                        username=username, nameStock=str(request.form.get("symbol")))[0]["quantity"]

        # Store the value of sale
        value = look["price"] * int(shares)

        # If the symbol searched or number of shares is invalid, return apology
        if not request.form.get("symbol") or look == None:
            return apology("you must provide a stock", 400)
        elif not shares or not shares.isdigit() or int(shares) < 1 or int(shares) > int(user_shares):
            return apology("share number is invalid", 400)

        # If everything checks, proceed with sale
        else:
            # Add the value of sale to the user's cash
            db.execute("UPDATE users SET cash = cash + :value WHERE id = :uid", value=value, uid=int(session['user_id']))

            # Add the transaction to the user's history
            db.execute("INSERT INTO history_bought (username, operation, symbol, price, shares) VALUES (:username, 'SELL', :symbol, :price, :shares)",
            username=username, symbol=look['symbol'], price=look['price'], shares=request.form.get('shares'))

            # If the user is selling all the shares, remove the stock from the user's portfolio
            if int(user_shares) == int(shares):
                db.execute("DELETE FROM actions WHERE username = :username and nameStock = :nameStock",
                            username=username, nameStock=str(request.form.get("symbol")))

            # If the user is just selling some of the shares, update the portfolio
            elif int(user_shares) > int(shares):
                db.execute("UPDATE actions SET quantity = :quantity WHERE username = :username and nameStock = :symbol",
                            quantity=shares, username=username, symbol=request.form.get("symbol"))

        # Send them to the portfolio
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Get the symbols from portfolio for the select list
        symbols = db.execute("SELECT nameStock FROM actions WHERE username = :username", username=username)

        return render_template("sell.html", symbols=symbols)



def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
