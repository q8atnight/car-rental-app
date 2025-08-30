"""A simple car rental management prototype.

This Flask application demonstrates a basic database‑backed system for
managing cars, customers and rental agreements. It isn’t meant to be
production ready, but it shows how your requirements could be modelled
in a structured way with a web interface for data entry.

To run the app locally:

    # Install dependencies (Flask and SQLAlchemy)
    pip install flask flask_sqlalchemy

    # Initialise the database
    python app.py --init-db

    # Start the development server
    python app.py

The app will be available at http://localhost:5000/.  You can add
customers, cars and rental agreements via simple forms.

Note: file uploads aren’t handled in this example – uploaded
documents are stored as filenames only. Integrating actual file
storage (e.g. to local disk or a cloud service) is left as an
exercise.
"""

import argparse
from datetime import datetime, date, timedelta

from flask import (Flask, abort, redirect, render_template, request,
                   url_for, flash, send_from_directory)
from flask_sqlalchemy import SQLAlchemy

# Import SQL functions for ordering logic
from sqlalchemy import func

import os


app = Flask(__name__)
app.config['SECRET_KEY'] = 'change‑me'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///car_rental.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'

db = SQLAlchemy(app)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    passport_file = db.Column(db.String(200))  # filename of uploaded passport
    license_file = db.Column(db.String(200))   # filename of uploaded licence

    rentals = db.relationship('Rental', back_populates='customer')
    fines = db.relationship('Fine', back_populates='customer')
    damages = db.relationship('Damage', back_populates='customer')

    def __repr__(self) -> str:
        return f"<Customer {self.name}>"


class Car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(120), nullable=False)
    model_year = db.Column(db.Integer)
    licence_plate = db.Column(db.String(20), unique=True)
    colour = db.Column(db.String(50))
    mileage_at_purchase = db.Column(db.Integer)
    purchase_price = db.Column(db.Float)
    initial_investment = db.Column(db.Float)
    salik_tag = db.Column(db.String(50))
    registration_date = db.Column(db.Date)
    tracker_installed = db.Column(db.Boolean, default=False)
    passing_cost = db.Column(db.Float)
    registration_cost = db.Column(db.Float)
    insurance_cost = db.Column(db.Float)
    planned_rent = db.Column(db.Float)

    rentals = db.relationship('Rental', back_populates='car')
    expenses = db.relationship('Expense', back_populates='car')
    fines = db.relationship('Fine', back_populates='car')
    damages = db.relationship('Damage', back_populates='car')

    def __repr__(self) -> str:
        return f"<Car {self.licence_plate}>"


class Rental(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)  # null for open ended
    contract_type = db.Column(db.String(20), default='open')  # open or fixed
    planned_rent = db.Column(db.Float)
    actual_rent = db.Column(db.Float)
    deposit = db.Column(db.Float)

    # When closing a rental the deposit may be partially or fully refunded.
    deposit_refunded = db.Column(db.Boolean, default=False)
    deposit_refunded_amount = db.Column(db.Float, nullable=True)
    deposit_refund_date = db.Column(db.Date, nullable=True)

    # Billing interval (in days) for recurring rental payments.  Defaults to 30
    # days (approximate one month).  Changing this allows for weekly or
    # quarterly billing schedules.  A corresponding ``next_billing_date``
    # indicates the next date on which rent is due.
    billing_interval_days = db.Column(db.Integer, default=30)
    next_billing_date = db.Column(db.Date, nullable=True)

    car = db.relationship('Car', back_populates='rentals')
    customer = db.relationship('Customer', back_populates='rentals')
    payments = db.relationship('Payment', back_populates='rental')

    def __repr__(self) -> str:
        return f"<Rental car={self.car_id} customer={self.customer_id}>"


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rental_id = db.Column(db.Integer, db.ForeignKey('rental.id'))
    amount = db.Column(db.Float)
    date = db.Column(db.Date, default=datetime.utcnow)
    location = db.Column(db.String(50))  # e.g. Dubai or Germany

    rental = db.relationship('Rental', back_populates='payments')

    def __repr__(self) -> str:
        return f"<Payment {self.amount} on {self.date}>"


# ---------------------------------------------------------------------------
# Additional tables to support car ordering and defleeting without changing
# existing Car columns.  Defleeting a car moves it to an archived list.  A
# separate table CarOrder holds an order index for each car so the list
# can be manually reordered in the UI.

class CarOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), unique=True)
    order_index = db.Column(db.Integer, default=0)
    car = db.relationship('Car', backref=db.backref('car_order', uselist=False))

class DefleetedCar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), unique=True)
    date = db.Column(db.Date, default=date.today)
    car = db.relationship('Car', backref=db.backref('defleet_record', uselist=False))


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    date = db.Column(db.Date, default=datetime.utcnow)
    category = db.Column(db.String(100))
    description = db.Column(db.Text)
    cost = db.Column(db.Float)
    recurring = db.Column(db.Boolean, default=False)
    next_due_date = db.Column(db.Date, nullable=True)

    car = db.relationship('Car', back_populates='expenses')

    def __repr__(self) -> str:
        return f"<Expense {self.category} {self.cost}>"


class Fine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    date = db.Column(db.Date, default=datetime.utcnow)
    description = db.Column(db.Text)
    amount = db.Column(db.Float)
    paid = db.Column(db.Boolean, default=False)
    settled_via = db.Column(db.String(50))  # rent or deposit

    car = db.relationship('Car', back_populates='fines')
    customer = db.relationship('Customer', back_populates='fines')

    def __repr__(self) -> str:
        return f"<Fine {self.amount} paid={self.paid}>"


class Damage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    date = db.Column(db.Date, default=datetime.utcnow)
    description = db.Column(db.Text)
    amount = db.Column(db.Float)
    paid = db.Column(db.Boolean, default=False)
    settled_via = db.Column(db.String(50))  # rent or deposit

    car = db.relationship('Car', back_populates='damages')
    customer = db.relationship('Customer', back_populates='damages')

    def __repr__(self) -> str:
        return f"<Damage {self.amount} paid={self.paid}>"


# ---------------------------------------------------------------------------
# Salik model to represent toll costs associated with a rental over a date range.
class Salik(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), nullable=False)
    rental_id = db.Column(db.Integer, db.ForeignKey('rental.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)

    # Track whether this Salik entry has been paid (either via rent or deposit). Defaults to False (outstanding).
    paid = db.Column(db.Boolean, default=False)

    # Record how the Salik cost was settled: 'rent' or 'deposit'. Optional.
    settled_via = db.Column(db.String(50))

    car = db.relationship('Car', backref=db.backref('salik', lazy=True))
    rental = db.relationship('Rental', backref=db.backref('salik_entries', lazy=True))

    def __repr__(self) -> str:
        return f"<Salik {self.amount} {self.start_date}-{self.end_date} paid={self.paid}>"


# ---------------------------------------------------------------------------
# Booking model used to reserve cars in advance without starting a rental.
# A booking has a start and end date and can optionally be tied to a customer.
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    note = db.Column(db.String(255))

    car = db.relationship('Car', backref=db.backref('bookings', lazy=True))
    customer = db.relationship('Customer', backref=db.backref('bookings', lazy=True))

    def __repr__(self) -> str:
        return f"<Booking {self.car_id} {self.start_date} to {self.end_date}>"


# ---------------------------------------------------------------------------
# Helper function to ensure every car has a corresponding ordering record.  If
# a new car is added without an order entry this will create one at the end
# of the list.  It also ensures that order indexes are consecutive so that
# moving cars up or down in the list behaves predictably.
def ensure_car_order():
    """Ensure each car has a CarOrder record and normalise indices."""
    # Create missing order entries and set order_index based on existing max
    max_index = db.session.query(func.max(CarOrder.order_index)).scalar() or 0
    existing_ids = {co.car_id for co in CarOrder.query.all()}
    for car in Car.query.all():
        if car.id not in existing_ids:
            max_index += 1
            db.session.add(CarOrder(car_id=car.id, order_index=max_index))
    db.session.commit()
    # Normalise indices to 1..N to avoid gaps; keeps current relative order
    ordered = CarOrder.query.order_by(CarOrder.order_index.asc()).all()
    for idx, co in enumerate(ordered, start=1):
        co.order_index = idx
    db.session.commit()


# ---------------------------------------------------------------------------
# Routes to reorder cars in the list.  Moving a car up swaps its order_index
# with the previous car; moving down swaps with the next.  These routes
# require POST because they modify data.
@app.route('/cars/move_up/<int:car_id>', methods=['POST'])
def move_car_up(car_id: int):
    ensure_car_order()
    current = CarOrder.query.filter_by(car_id=car_id).first()
    if current is None:
        return redirect(url_for('list_cars'))
    # Find the car above (lower order index)
    prev = CarOrder.query.filter(CarOrder.order_index < current.order_index).order_by(CarOrder.order_index.desc()).first()
    if prev:
        current.order_index, prev.order_index = prev.order_index, current.order_index
        db.session.commit()
    return redirect(url_for('list_cars'))


@app.route('/cars/move_down/<int:car_id>', methods=['POST'])
def move_car_down(car_id: int):
    ensure_car_order()
    current = CarOrder.query.filter_by(car_id=car_id).first()
    if current is None:
        return redirect(url_for('list_cars'))
    # Find the car below (higher order index)
    nxt = CarOrder.query.filter(CarOrder.order_index > current.order_index).order_by(CarOrder.order_index.asc()).first()
    if nxt:
        current.order_index, nxt.order_index = nxt.order_index, current.order_index
        db.session.commit()
    return redirect(url_for('list_cars'))


# ---------------------------------------------------------------------------
# Defleet route.  Moves a car out of the active fleet into the defleeted
# listing.  A car cannot be defleeted if it currently has an active rental
# (an unrefunded deposit or an open rental period).  Defleet records are
# stored in DefleetedCar and prevent the car from showing in the main list.
@app.route('/cars/defleet/<int:car_id>', methods=['POST'])
def defleet_car(car_id: int):
    car = Car.query.get_or_404(car_id)
    today = date.today()
    # Check for active rental on this car.  A rental is active if it has
    # not been settled and its end date is in the future (or open).
    for rental in car.rentals:
        if not rental.deposit_refunded and (rental.end_date is None or rental.end_date >= today):
            flash('Cannot defleet a car that is currently rented. Settle the rental first.')
            return redirect(url_for('list_cars'))
    # Add defleet record if not already defleeted
    if car.defleet_record is None:
        rec = DefleetedCar(car_id=car.id, date=today)
        db.session.add(rec)
        db.session.commit()
        flash('Car has been defleeted.')
    return redirect(url_for('list_cars'))


# ---------------------------------------------------------------------------
# Serve uploaded documents from the uploads directory.  Allows viewing and
# downloading passport and licence files associated with customers.
@app.route('/uploads/<path:filename>')
def uploaded_file(filename: str):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)


# ---------------------------------------------------------------------------
# List of defleeted cars.  Shows all cars that have been removed from the
# active fleet.  These cars cannot be edited or defleeted again until
# reinstated (future feature).
@app.route('/cars/defleeted')
def list_defleeted_cars():
    # Join car with defleeted record to fetch defleet date
    cars = db.session.query(Car).join(DefleetedCar).all()
    return render_template('cars_defleeted.html', cars=cars)


# ---------------------------------------------------------------------------
# Settled rentals listing.  Shows rentals where the deposit has been fully
# refunded (i.e. settled).  These rentals are separated from active rentals
# to reduce clutter on the main rentals page.
@app.route('/rentals/settled')
def list_settled_rentals():
    rentals = Rental.query.filter_by(deposit_refunded=True).all()
    return render_template('settled_rentals.html', rentals=rentals)


@app.route('/')
def index():
    """
    Dashboard home page. Provides high‑level metrics including number of cars
    rented/available/booked today, upcoming registration renewals within the
    next 30 days, overdue rent payments, and totals of unpaid fines, damages
    and Salik costs for the current month.
    """
    today = date.today()
    cars = Car.query.all()
    total_cars = len(cars)
    rented_count = sum(1 for c in cars if is_rented_today(c, today))
    booked_count = sum(1 for c in cars if (not is_rented_today(c, today)) and is_booked_today(c, today))
    available_count = total_cars - rented_count - booked_count

    # upcoming renewals: currently only based on registration_date
    soon = today + timedelta(days=30)
    upcoming_renewals = []
    for c in cars:
        if c.registration_date and today <= c.registration_date <= soon:
            upcoming_renewals.append({'car': c, 'type': 'Registration', 'date': c.registration_date})
    upcoming_renewals.sort(key=lambda x: x['date'])

    # overdue rentals: rentals where last payment older than 30 days or no payment
    overdue_rentals = []
    rentals = Rental.query.all()
    for r in rentals:
        # only consider active rentals (no end date or end date >= today)
        if r.start_date and (r.end_date is None or r.end_date >= today):
            last_payment_date = None
            # sort payments by date to find last
            for p in sorted(r.payments, key=lambda p: p.date or date.min):
                last_payment_date = p.date
            if last_payment_date is None or (last_payment_date and (today - last_payment_date).days > 30):
                overdue_rentals.append(r)

    # unpaid fines and damages totals
    unpaid_fines = Fine.query.filter_by(paid=False).all()
    unpaid_damages = Damage.query.filter_by(paid=False).all()
    # salik expense summary for current month (category contains 'salik')
    month_start = date(today.year, today.month, 1)
    next_month = (month_start.replace(day=28) + timedelta(days=10)).replace(day=1)
    month_end = next_month - timedelta(days=1)
    salik_expenses = Expense.query.filter(
        Expense.date >= month_start,
        Expense.date <= month_end,
        Expense.category.ilike('%salik%')
    ).all()
    totals = {
        'unpaid_fines': sum(f.amount or 0 for f in unpaid_fines),
        'unpaid_damages': sum(d.amount or 0 for d in unpaid_damages),
        'salik_unpaid_month': sum(e.cost or 0 for e in salik_expenses),
    }
    return render_template('index.html',
                           total_cars=total_cars,
                           rented=rented_count,
                           booked=booked_count,
                           available=available_count,
                           upcoming_renewals=upcoming_renewals,
                           overdue_rentals=overdue_rentals,
                           totals=totals,
                           today=today)


@app.route('/customers')
def list_customers():
    customers = Customer.query.all()
    return render_template('customers.html', customers=customers)


@app.route('/customers/add', methods=['GET', 'POST'])
def add_customer():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form.get('phone')
        address = request.form.get('address')
        # Handle file uploads. Save to UPLOAD_FOLDER and store filename
        passport_file_obj = request.files.get('passport_file')
        license_file_obj = request.files.get('license_file')
        passport_filename = None
        license_filename = None
        import os
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        if passport_file_obj and passport_file_obj.filename:
            passport_filename = f"passport_{datetime.utcnow().timestamp()}_{passport_file_obj.filename}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], passport_filename)
            passport_file_obj.save(save_path)
        if license_file_obj and license_file_obj.filename:
            license_filename = f"license_{datetime.utcnow().timestamp()}_{license_file_obj.filename}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], license_filename)
            license_file_obj.save(save_path)
        customer = Customer(name=name, phone=phone, address=address,
                            passport_file=passport_filename, license_file=license_filename)
        db.session.add(customer)
        db.session.commit()
        return redirect(url_for('list_customers'))
    return render_template('add_customer.html')


@app.route('/customers/edit/<int:customer_id>', methods=['GET', 'POST'])
def edit_customer(customer_id: int):
    customer = Customer.query.get_or_404(customer_id)
    if request.method == 'POST':
        customer.name = request.form['name']
        customer.phone = request.form.get('phone')
        customer.address = request.form.get('address')
        # handle file uploads (replace existing files if provided)
        passport_file_obj = request.files.get('passport_file')
        license_file_obj = request.files.get('license_file')
        import os
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        if passport_file_obj and passport_file_obj.filename:
            passport_filename = f"passport_{datetime.utcnow().timestamp()}_{passport_file_obj.filename}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], passport_filename)
            passport_file_obj.save(save_path)
            customer.passport_file = passport_filename
        if license_file_obj and license_file_obj.filename:
            license_filename = f"license_{datetime.utcnow().timestamp()}_{license_file_obj.filename}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], license_filename)
            license_file_obj.save(save_path)
            customer.license_file = license_filename
        db.session.commit()
        return redirect(url_for('list_customers'))
    return render_template('edit_customer.html', customer=customer)


@app.route('/customers/delete/<int:customer_id>', methods=['POST'])
def delete_customer(customer_id: int):
    customer = Customer.query.get_or_404(customer_id)
    db.session.delete(customer)
    db.session.commit()
    return redirect(url_for('list_customers'))


@app.route('/cars')
def list_cars():
    """
    Display the list of active (non-defleeted) cars.  Cars are ordered
    according to their CarOrder record.  A summary of the fleet is
    computed and displayed above the table, including total car count,
    average age, total initial value, sum of planned rents and total
    expenses.  Each car row also displays its total value and total
    expenses along with controls to reorder (up/down), defleet, add
    expenses, view expenses and edit/delete the car.
    """
    ensure_car_order()
    # Join car with order and defleet tables to sort and filter
    query = (db.session.query(Car)
             .outerjoin(CarOrder, Car.id == CarOrder.car_id)
             .outerjoin(DefleetedCar, Car.id == DefleetedCar.car_id))
    cars = query.filter(DefleetedCar.id.is_(None)).order_by(CarOrder.order_index.asc()).all()
    # Compute per-car totals and global summary
    car_infos = []
    total_initial_value = 0.0
    total_planned_rent = 0.0
    total_expenses_sum = 0.0
    age_values = []
    current_year = date.today().year
    for car in cars:
        total_value = (car.purchase_price or 0.0) + (car.initial_investment or 0.0)
        total_expenses = sum(exp.cost or 0.0 for exp in car.expenses)
        car_infos.append({'car': car, 'total_value': total_value, 'total_expenses': total_expenses})
        total_initial_value += total_value
        total_planned_rent += (car.planned_rent or 0.0)
        total_expenses_sum += total_expenses
        if car.model_year:
            age_values.append(current_year - car.model_year)
    summary = {
        'total_cars': len(cars),
        'average_age': (sum(age_values) / len(age_values)) if age_values else None,
        'total_initial_value': total_initial_value,
        'total_planned_rent': total_planned_rent,
        'total_expenses': total_expenses_sum
    }
    return render_template('cars.html', car_infos=car_infos, summary=summary)


@app.route('/cars/add', methods=['GET', 'POST'])
def add_car():
    if request.method == 'POST':
        model = request.form['model']
        model_year = request.form.get('model_year')
        licence_plate = request.form.get('licence_plate')
        colour = request.form.get('colour')
        mileage = request.form.get('mileage_at_purchase')
        purchase_price = request.form.get('purchase_price')
        initial_inv = request.form.get('initial_investment')
        salik_tag = request.form.get('salik_tag')
        reg_date = request.form.get('registration_date')
        tracker = request.form.get('tracker_installed') == 'on'
        passing_cost = request.form.get('passing_cost')
        registration_cost = request.form.get('registration_cost')
        insurance_cost = request.form.get('insurance_cost')
        planned_rent = request.form.get('planned_rent')

        car = Car(
            model=model,
            model_year=int(model_year) if model_year else None,
            licence_plate=licence_plate,
            colour=colour,
            mileage_at_purchase=int(mileage) if mileage else None,
            purchase_price=float(purchase_price) if purchase_price else None,
            initial_investment=float(initial_inv) if initial_inv else None,
            salik_tag=salik_tag,
            # Parse registration date in European format (DD/MM/YYYY)
            registration_date=datetime.strptime(reg_date, '%d/%m/%Y').date() if reg_date else None,
            tracker_installed=tracker,
            passing_cost=float(passing_cost) if passing_cost else None,
            registration_cost=float(registration_cost) if registration_cost else None,
            insurance_cost=float(insurance_cost) if insurance_cost else None,
            planned_rent=float(planned_rent) if planned_rent else None,
        )
        db.session.add(car)
        db.session.commit()
        # Assign ordering for the new car at the end of the list
        ensure_car_order()
        max_index = db.session.query(func.max(CarOrder.order_index)).scalar() or 0
        # Only create a CarOrder if one does not exist (should not for new cars)
        if not CarOrder.query.filter_by(car_id=car.id).first():
            db.session.add(CarOrder(car_id=car.id, order_index=max_index + 1))
            db.session.commit()
        return redirect(url_for('list_cars'))
    return render_template('add_car.html')


@app.route('/cars/edit/<int:car_id>', methods=['GET', 'POST'])
def edit_car(car_id: int):
    """Edit an existing car."""
    car = Car.query.get_or_404(car_id)
    if request.method == 'POST':
        car.model = request.form['model']
        model_year = request.form.get('model_year')
        car.model_year = int(model_year) if model_year else None
        car.licence_plate = request.form.get('licence_plate')
        car.colour = request.form.get('colour')
        mileage = request.form.get('mileage_at_purchase')
        car.mileage_at_purchase = int(mileage) if mileage else None
        purchase_price = request.form.get('purchase_price')
        car.purchase_price = float(purchase_price) if purchase_price else None
        initial_inv = request.form.get('initial_investment')
        car.initial_investment = float(initial_inv) if initial_inv else None
        car.salik_tag = request.form.get('salik_tag')
        reg_date = request.form.get('registration_date')
        # Parse registration date in European format
        car.registration_date = datetime.strptime(reg_date, '%d/%m/%Y').date() if reg_date else None
        car.tracker_installed = request.form.get('tracker_installed') == 'on'
        passing_cost = request.form.get('passing_cost')
        car.passing_cost = float(passing_cost) if passing_cost else None
        registration_cost = request.form.get('registration_cost')
        car.registration_cost = float(registration_cost) if registration_cost else None
        insurance_cost = request.form.get('insurance_cost')
        car.insurance_cost = float(insurance_cost) if insurance_cost else None
        planned_rent = request.form.get('planned_rent')
        car.planned_rent = float(planned_rent) if planned_rent else None
        db.session.commit()
        return redirect(url_for('list_cars'))
    return render_template('edit_car.html', car=car)


@app.route('/cars/delete/<int:car_id>', methods=['POST'])
def delete_car(car_id: int):
    car = Car.query.get_or_404(car_id)
    # Remove associated ordering and defleet records
    CarOrder.query.filter_by(car_id=car.id).delete()
    DefleetedCar.query.filter_by(car_id=car.id).delete()
    db.session.delete(car)
    db.session.commit()
    return redirect(url_for('list_cars'))


@app.route('/rentals')
def list_rentals():
    """
    Display the list of active and upcoming rentals.  Settled rentals (those
    with refunded deposits) are excluded from this view and appear in the
    separate 'Settled Rentals' section.  Sorting by start date keeps
    current rentals at the top.
    """
    rentals = Rental.query.filter_by(deposit_refunded=False).order_by(Rental.start_date.asc()).all()
    return render_template('rentals.html', rentals=rentals)


@app.route('/rentals/add', methods=['GET', 'POST'])
def add_rental():
    cars = Car.query.all()
    customers = Customer.query.all()
    if request.method == 'POST':
        car_id = int(request.form['car_id'])
        customer_id = int(request.form['customer_id'])
        # Parse dates in European format (DD/MM/YYYY)
        start_date = datetime.strptime(request.form['start_date'], '%d/%m/%Y').date()
        end_date_str = request.form.get('end_date')
        end_date = datetime.strptime(end_date_str, '%d/%m/%Y').date() if end_date_str else None
        contract_type = 'fixed' if end_date else 'open'
        planned_rent = request.form.get('planned_rent')
        actual_rent = request.form.get('actual_rent')
        deposit = request.form.get('deposit')

        # Check if the selected car already has an overlapping rental.  A rental
        # overlaps if its start is before or on the new rental end (or open ended)
        # and its end (if any) is after or on the new rental start.  We allow
        # creating a new rental if the existing rental's end date is before the
        # new start date.
        overlapping = False
        existing_rentals = Rental.query.filter_by(car_id=car_id).all()
        for r in existing_rentals:
            # Skip if the rental is the same (should not occur on add)
            # Determine r's end for comparison
            r_end = r.end_date or date.max
            new_end = end_date or date.max
            # Overlap occurs when ranges intersect
            if r.start_date <= new_end and start_date <= r_end:
                overlapping = True
                conflict_rental = r
                break
        if overlapping:
            flash(f"This car is already assigned to another rental (start {conflict_rental.start_date.strftime('%d/%m/%Y')} to {'Open' if not conflict_rental.end_date else conflict_rental.end_date.strftime('%d/%m/%Y')}). Please choose a different car or adjust dates.")
            return render_template('add_rental.html', cars=cars, customers=customers)

        rental = Rental(
            car_id=car_id,
            customer_id=customer_id,
            start_date=start_date,
            end_date=end_date,
            contract_type=contract_type,
            planned_rent=float(planned_rent) if planned_rent else None,
            actual_rent=float(actual_rent) if actual_rent else None,
            deposit=float(deposit) if deposit else None,
        )
        # Initialize billing interval and next billing date
        rental.billing_interval_days = 30
        rental.next_billing_date = start_date + timedelta(days=rental.billing_interval_days)
        db.session.add(rental)
        db.session.commit()
        return redirect(url_for('list_rentals'))
    return render_template('add_rental.html', cars=cars, customers=customers)


@app.route('/rentals/edit/<int:rental_id>', methods=['GET', 'POST'])
def edit_rental(rental_id: int):
    rental = Rental.query.get_or_404(rental_id)
    cars = Car.query.all()
    customers = Customer.query.all()
    if request.method == 'POST':
        rental.car_id = int(request.form['car_id'])
        rental.customer_id = int(request.form['customer_id'])
        start_date = datetime.strptime(request.form['start_date'], '%d/%m/%Y').date()
        end_date_str = request.form.get('end_date')
        end_date = datetime.strptime(end_date_str, '%d/%m/%Y').date() if end_date_str else None
        rental.start_date = start_date
        rental.end_date = end_date
        rental.contract_type = 'fixed' if end_date else 'open'
        planned_rent = request.form.get('planned_rent')
        actual_rent = request.form.get('actual_rent')
        deposit = request.form.get('deposit')
        rental.planned_rent = float(planned_rent) if planned_rent else None
        rental.actual_rent = float(actual_rent) if actual_rent else None
        rental.deposit = float(deposit) if deposit else None
        db.session.commit()
        return redirect(url_for('list_rentals'))
    # Format dates for display
    start = rental.start_date.strftime('%d/%m/%Y') if rental.start_date else ''
    end = rental.end_date.strftime('%d/%m/%Y') if rental.end_date else ''
    return render_template('edit_rental.html', rental=rental, cars=cars, customers=customers, start=start, end=end)


@app.route('/rentals/delete/<int:rental_id>', methods=['POST'])
def delete_rental(rental_id: int):
    rental = Rental.query.get_or_404(rental_id)
    db.session.delete(rental)
    db.session.commit()
    return redirect(url_for('list_rentals'))


@app.route('/payments/add/<int:rental_id>', methods=['GET', 'POST'])
def add_payment(rental_id):
    """
    Add a payment for a rental.  In addition to capturing the amount, date and
    location of the payment, this route also allows the user to allocate the
    payment against any outstanding fines, damages or Salik entries for the
    rental.  When an item is selected, it will be marked as paid and its
    ``settled_via`` field will be set to 'rent'.  This makes it easy to
    reconcile extra charges with the monthly rent payment.

    The page shows a list of unpaid charges (fines, damages, Salik) with
    checkboxes.  The user can tick the ones that are covered by this
    payment.  Unchecked items remain outstanding and will appear in future
    due summaries or settlements.
    """
    rental = Rental.query.get_or_404(rental_id)
    # Gather outstanding fines, damages and salik for this rental
    outstanding_fines = [f for f in rental.customer.fines if f.car_id == rental.car_id and not f.paid]
    outstanding_damages = [d for d in rental.customer.damages if d.car_id == rental.car_id and not d.paid]
    outstanding_salik = [s for s in rental.salik_entries if not getattr(s, 'paid', False)]
    if request.method == 'POST':
        amount = float(request.form['amount'])
        pay_date = datetime.strptime(request.form['date'], '%d/%m/%Y').date()
        location = request.form.get('location')
        payment = Payment(rental_id=rental.id, amount=amount, date=pay_date, location=location)
        db.session.add(payment)
        # Process selected fines/damages/salik: mark as paid via rent
        # request.form.getlist returns list of strings for the given name
        selected_fines = request.form.getlist('fine_ids')
        selected_damages = request.form.getlist('damage_ids')
        selected_salik = request.form.getlist('salik_ids')
        # Mark fines
        for fid in selected_fines:
            fine_obj = Fine.query.get(int(fid))
            if fine_obj:
                fine_obj.paid = True
                fine_obj.settled_via = 'rent'
        # Mark damages
        for did in selected_damages:
            dmg_obj = Damage.query.get(int(did))
            if dmg_obj:
                dmg_obj.paid = True
                dmg_obj.settled_via = 'rent'
        # Mark salik
        for sid in selected_salik:
            salik_obj = Salik.query.get(int(sid))
            if salik_obj:
                salik_obj.paid = True
                salik_obj.settled_via = 'rent'
        db.session.commit()
        return redirect(url_for('list_rentals'))
    return render_template('add_payment.html', rental=rental,
                           outstanding_fines=outstanding_fines,
                           outstanding_damages=outstanding_damages,
                           outstanding_salik=outstanding_salik)


@app.route('/payments/edit/<int:payment_id>', methods=['GET', 'POST'])
def edit_payment(payment_id: int):
    payment = Payment.query.get_or_404(payment_id)
    rental = payment.rental
    if request.method == 'POST':
        payment.amount = float(request.form['amount'])
        payment.date = datetime.strptime(request.form['date'], '%d/%m/%Y').date()
        payment.location = request.form.get('location')
        db.session.commit()
        return redirect(url_for('list_payments_for_rental', rental_id=rental.id))
    return render_template('edit_payment.html', payment=payment, rental=rental)


@app.route('/payments/delete/<int:payment_id>', methods=['POST'])
def delete_payment(payment_id: int):
    payment = Payment.query.get_or_404(payment_id)
    rental_id = payment.rental_id
    db.session.delete(payment)
    db.session.commit()
    return redirect(url_for('list_payments_for_rental', rental_id=rental_id))


@app.route('/payments/rental/<int:rental_id>')
def list_payments_for_rental(rental_id: int):
    rental = Rental.query.get_or_404(rental_id)
    payments = rental.payments
    return render_template('payments_list.html', rental=rental, payments=payments)


@app.route('/expenses/add/<int:car_id>', methods=['GET', 'POST'])
def add_expense(car_id):
    car = Car.query.get_or_404(car_id)
    if request.method == 'POST':
        date = datetime.strptime(request.form['date'], '%d/%m/%Y').date()
        category = request.form['category']
        description = request.form.get('description')
        cost = float(request.form['cost'])
        recurring = request.form.get('recurring') == 'on'
        next_due = request.form.get('next_due_date')
        next_due_date = datetime.strptime(next_due, '%d/%m/%Y').date() if next_due else None
        expense = Expense(car_id=car.id, date=date, category=category,
                          description=description, cost=cost,
                          recurring=recurring, next_due_date=next_due_date)
        db.session.add(expense)
        db.session.commit()
        return redirect(url_for('list_cars'))
    return render_template('add_expense.html', car=car)


# ---------------------------------------------------------------------------
# Expense management and overview

@app.route('/expenses')
def expenses_overview():
    """Show total expenses per car."""
    cars = Car.query.all()
    rows = []
    for car in cars:
        total = sum(e.cost or 0 for e in car.expenses)
        rows.append({'car': car, 'total': total})
    return render_template('expenses_overview.html', rows=rows)


@app.route('/expenses/car/<int:car_id>')
def expenses_by_car(car_id: int):
    car = Car.query.get_or_404(car_id)
    expenses = car.expenses
    return render_template('expenses_list.html', car=car, expenses=expenses)


@app.route('/expenses/edit/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id: int):
    expense = Expense.query.get_or_404(expense_id)
    car = expense.car
    if request.method == 'POST':
        expense.date = datetime.strptime(request.form['date'], '%d/%m/%Y').date()
        expense.category = request.form['category']
        expense.description = request.form.get('description')
        expense.cost = float(request.form['cost'])
        expense.recurring = request.form.get('recurring') == 'on'
        next_due = request.form.get('next_due_date')
        expense.next_due_date = datetime.strptime(next_due, '%d/%m/%Y').date() if next_due else None
        db.session.commit()
        return redirect(url_for('expenses_by_car', car_id=car.id))
    # Format date strings for display
    date_str = expense.date.strftime('%d/%m/%Y') if expense.date else ''
    next_due_str = expense.next_due_date.strftime('%d/%m/%Y') if expense.next_due_date else ''
    return render_template('edit_expense.html', expense=expense, car=car, date_str=date_str, next_due_str=next_due_str)


@app.route('/expenses/delete/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id: int):
    expense = Expense.query.get_or_404(expense_id)
    car_id = expense.car_id
    db.session.delete(expense)
    db.session.commit()
    return redirect(url_for('expenses_by_car', car_id=car_id))


@app.route('/fines/add/<int:car_id>/<int:customer_id>', methods=['GET', 'POST'])
def add_fine(car_id, customer_id):
    car = Car.query.get_or_404(car_id)
    customer = Customer.query.get_or_404(customer_id)
    if request.method == 'POST':
        date = datetime.strptime(request.form['date'], '%d/%m/%Y').date()
        description = request.form.get('description')
        amount = float(request.form['amount'])
        paid = request.form.get('paid') == 'on'
        settled_via = request.form.get('settled_via')
        fine = Fine(car_id=car.id, customer_id=customer.id, date=date,
                    description=description, amount=amount,
                    paid=paid, settled_via=settled_via)
        db.session.add(fine)
        db.session.commit()
        return redirect(url_for('list_rentals'))
    return render_template('add_fine.html', car=car, customer=customer)


@app.route('/fines/edit/<int:fine_id>', methods=['GET', 'POST'])
def edit_fine(fine_id: int):
    fine = Fine.query.get_or_404(fine_id)
    car = fine.car
    customer = fine.customer
    if request.method == 'POST':
        fine.date = datetime.strptime(request.form['date'], '%d/%m/%Y').date()
        fine.description = request.form.get('description')
        fine.amount = float(request.form['amount'])
        fine.paid = request.form.get('paid') == 'on'
        fine.settled_via = request.form.get('settled_via')
        db.session.commit()
        return redirect(url_for('list_rentals'))
    date_str = fine.date.strftime('%d/%m/%Y') if fine.date else ''
    return render_template('edit_fine.html', fine=fine, car=car, customer=customer, date_str=date_str)


@app.route('/fines/delete/<int:fine_id>', methods=['POST'])
def delete_fine(fine_id: int):
    fine = Fine.query.get_or_404(fine_id)
    db.session.delete(fine)
    db.session.commit()
    return redirect(url_for('list_rentals'))


@app.route('/fines/rental/<int:rental_id>')
def list_fines_for_rental(rental_id: int):
    rental = Rental.query.get_or_404(rental_id)
    # Only fines for this car and customer during this rental period
    fines = [f for f in rental.customer.fines if f.car_id == rental.car_id]
    return render_template('fines_list.html', rental=rental, fines=fines)


@app.route('/damages/add/<int:car_id>/<int:customer_id>', methods=['GET', 'POST'])
def add_damage(car_id, customer_id):
    car = Car.query.get_or_404(car_id)
    customer = Customer.query.get_or_404(customer_id)
    if request.method == 'POST':
        date = datetime.strptime(request.form['date'], '%d/%m/%Y').date()
        description = request.form.get('description')
        amount = float(request.form['amount'])
        paid = request.form.get('paid') == 'on'
        settled_via = request.form.get('settled_via')
        damage = Damage(car_id=car.id, customer_id=customer.id, date=date,
                        description=description, amount=amount,
                        paid=paid, settled_via=settled_via)
        db.session.add(damage)
        db.session.commit()
        return redirect(url_for('list_rentals'))
    return render_template('add_damage.html', car=car, customer=customer)


@app.route('/damages/edit/<int:damage_id>', methods=['GET', 'POST'])
def edit_damage(damage_id: int):
    damage = Damage.query.get_or_404(damage_id)
    car = damage.car
    customer = damage.customer
    if request.method == 'POST':
        damage.date = datetime.strptime(request.form['date'], '%d/%m/%Y').date()
        damage.description = request.form.get('description')
        damage.amount = float(request.form['amount'])
        damage.paid = request.form.get('paid') == 'on'
        damage.settled_via = request.form.get('settled_via')
        db.session.commit()
        return redirect(url_for('list_rentals'))
    date_str = damage.date.strftime('%d/%m/%Y') if damage.date else ''
    return render_template('edit_damage.html', damage=damage, car=car, customer=customer, date_str=date_str)


@app.route('/damages/delete/<int:damage_id>', methods=['POST'])
def delete_damage(damage_id: int):
    damage = Damage.query.get_or_404(damage_id)
    db.session.delete(damage)
    db.session.commit()
    return redirect(url_for('list_rentals'))


@app.route('/damages/rental/<int:rental_id>')
def list_damages_for_rental(rental_id: int):
    rental = Rental.query.get_or_404(rental_id)
    damages = [d for d in rental.customer.damages if d.car_id == rental.car_id]
    return render_template('damages_list.html', rental=rental, damages=damages)


# ---------------------------------------------------------------------------
# Bookings and availability

@app.route('/bookings')
def list_bookings():
    """List all bookings."""
    bookings = Booking.query.order_by(Booking.start_date.desc()).all()
    return render_template('bookings.html', bookings=bookings)


@app.route('/bookings/add', methods=['GET', 'POST'])
def add_booking():
    """Add a new booking. A booking reserves a car for a date range, optionally for a customer."""
    cars = Car.query.order_by(Car.licence_plate.asc()).all()
    customers = Customer.query.order_by(Customer.name.asc()).all()
    if request.method == 'POST':
        car_id = int(request.form['car_id'])
        customer_id = request.form.get('customer_id')
        cust_id_val = int(customer_id) if customer_id else None
        start_date = datetime.strptime(request.form['start_date'], '%d/%m/%Y').date()
        end_date = datetime.strptime(request.form['end_date'], '%d/%m/%Y').date()
        note = request.form.get('note')
        # Check if the car has an active rental whose end date overlaps the booking start
        conflict_rental = None
        rentals_for_car = Rental.query.filter_by(car_id=car_id).all()
        for r in rentals_for_car:
            # A rental is active if it started and has not ended yet (or ends in future)
            if r.start_date and (r.end_date is None or r.end_date >= start_date):
                # Only consider conflict if rental started before or on the booking start date
                if r.start_date <= start_date:
                    conflict_rental = r
                    break
        if conflict_rental and conflict_rental.end_date and conflict_rental.end_date >= start_date:
            # Warn the user that booking overlaps existing rental
            from flask import flash
            flash(f"Selected start date overlaps an active rental for this car which ends on {conflict_rental.end_date.strftime('%d/%m/%Y')}. Please adjust the booking dates.")
            return render_template('add_booking.html', cars=cars, customers=customers)
        # Otherwise proceed to create booking
        b = Booking(car_id=car_id, customer_id=cust_id_val,
                    start_date=start_date, end_date=end_date, note=note)
        db.session.add(b)
        db.session.commit()
        return redirect(url_for('list_bookings'))
    return render_template('add_booking.html', cars=cars, customers=customers)


@app.route('/bookings/edit/<int:booking_id>', methods=['GET', 'POST'])
def edit_booking(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)
    cars = Car.query.order_by(Car.licence_plate.asc()).all()
    customers = Customer.query.order_by(Customer.name.asc()).all()
    if request.method == 'POST':
        booking.car_id = int(request.form['car_id'])
        cust_id = request.form.get('customer_id')
        booking.customer_id = int(cust_id) if cust_id else None
        booking.start_date = datetime.strptime(request.form['start_date'], '%d/%m/%Y').date()
        booking.end_date = datetime.strptime(request.form['end_date'], '%d/%m/%Y').date()
        booking.note = request.form.get('note')
        db.session.commit()
        return redirect(url_for('list_bookings'))
    start = booking.start_date.strftime('%d/%m/%Y') if booking.start_date else ''
    end = booking.end_date.strftime('%d/%m/%Y') if booking.end_date else ''
    return render_template('edit_booking.html', booking=booking, cars=cars, customers=customers, start=start, end=end)


@app.route('/bookings/delete/<int:booking_id>', methods=['POST'])
def delete_booking(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)
    db.session.delete(booking)
    db.session.commit()
    return redirect(url_for('list_bookings'))


@app.route('/availability')
def availability():
    """
    Show availability status for all cars for today.  In addition to
    whether a car is rented, booked or available, provide information on
    when a rented car will next become available or if the rental is
    open ended.  This helps users plan future bookings.
    """
    today = date.today()
    # Sort cars by custom ordering and exclude defleeted cars
    ensure_car_order()
    query = (db.session.query(Car)
             .outerjoin(CarOrder, Car.id == CarOrder.car_id)
             .outerjoin(DefleetedCar, Car.id == DefleetedCar.car_id))
    cars = query.filter(DefleetedCar.id.is_(None)).order_by(CarOrder.order_index.asc()).all()
    rows = []
    for c in cars:
        status = 'Available'
        info = ''
        if is_rented_today(c, today):
            status = 'Rented'
            # Determine the active rental overlapping today
            active_rental = None
            for r in c.rentals:
                if r.start_date and (r.end_date is None or r.end_date >= today) and r.start_date <= today:
                    active_rental = r
                    break
            if active_rental:
                if active_rental.end_date:
                    # Show when the car will be free again (the day after end date)
                    available_date = active_rental.end_date + timedelta(days=1)
                    info = f"Available from {available_date.strftime('%d/%m/%Y')}"
                else:
                    info = "Open ended"
        elif is_booked_today(c, today):
            status = 'Booked'
            # Determine the active booking overlapping today
            active_booking = None
            for b in c.bookings:
                if date_in_range(today, b.start_date, b.end_date):
                    active_booking = b
                    break
            if active_booking:
                info = f"Booked until {active_booking.end_date.strftime('%d/%m/%Y')}"
        else:
            status = 'Available'
            info = ''
        rows.append({'car': c, 'status': status, 'info': info})
    return render_template('availability.html', rows=rows, today=today)


# ---------------------------------------------------------------------------
# Rental settlement – close a rental and handle deposit refund and charge settlement

@app.route('/rental/settle/<int:rental_id>', methods=['GET', 'POST'])
def settle_rental(rental_id: int):
    """
    Close a rental by applying outstanding fines and damages against the deposit
    and calculating any refund due to the customer. Displays a confirmation
    form on GET and performs the settlement on POST.
    """
    rental = Rental.query.get_or_404(rental_id)
    # Determine all fines/damages linked to this rental's car/customer that are unpaid
    outstanding_fines = [f for f in rental.customer.fines if f.car_id == rental.car_id and not f.paid]
    outstanding_damages = [d for d in rental.customer.damages if d.car_id == rental.car_id and not d.paid]
    # Determine all unpaid Salik entries for this rental
    outstanding_salik = [s for s in rental.salik_entries if not getattr(s, 'paid', False)]
    total_charges = (sum(f.amount or 0 for f in outstanding_fines) +
                     sum(d.amount or 0 for d in outstanding_damages) +
                     sum(s.amount or 0 for s in outstanding_salik))
    deposit = rental.deposit or 0
    refundable = max(deposit - total_charges, 0)
    if request.method == 'POST':
        # Mark fines/damages as settled via deposit and paid
        for f in outstanding_fines:
            f.paid = True
            f.settled_via = 'deposit'
        for d in outstanding_damages:
            d.paid = True
            d.settled_via = 'deposit'
        # Mark Salik entries as settled via deposit and paid
        for s in outstanding_salik:
            s.paid = True
            s.settled_via = 'deposit'
        # Record deposit refund
        rental.deposit_refunded = True
        rental.deposit_refunded_amount = refundable
        rental.deposit_refund_date = date.today()
        # If an end date is not provided, set to today to close the rental
        if rental.end_date is None:
            rental.end_date = date.today()
            rental.contract_type = 'fixed'
        db.session.commit()
        return redirect(url_for('list_rentals'))
    return render_template('settle_rental.html', rental=rental,
                           outstanding_fines=outstanding_fines,
                           outstanding_damages=outstanding_damages,
                           outstanding_salik=outstanding_salik,
                           total_charges=total_charges,
                           refundable=refundable)


# ---------------------------------------------------------------------------
# Salik: add, edit and delete

@app.route('/salik/add/<int:rental_id>', methods=['GET', 'POST'])
def add_salik(rental_id: int):
    """
    Add a Salik cost for a rental. A Salik entry records toll costs over
    a specific date range. The cost will be associated with the rental's
    car and the rental itself.
    """
    rental = Rental.query.get_or_404(rental_id)
    if request.method == 'POST':
        start_date = datetime.strptime(request.form['start_date'], '%d/%m/%Y').date()
        end_date = datetime.strptime(request.form['end_date'], '%d/%m/%Y').date()
        amount = float(request.form['amount'])
        paid_flag = True if request.form.get('paid') == 'on' else False
        settled_via = request.form.get('settled_via') or None
        s = Salik(car_id=rental.car_id, rental_id=rental_id,
                  start_date=start_date, end_date=end_date, amount=amount,
                  paid=paid_flag, settled_via=settled_via)
        db.session.add(s)
        db.session.commit()
        return redirect(url_for('list_rentals'))
    # Pre-fill suggestion: start date as rental start and end date as rental end or today
    default_start = rental.start_date.strftime('%d/%m/%Y')
    default_end = (rental.end_date or date.today()).strftime('%d/%m/%Y')
    return render_template('add_salik.html', rental=rental,
                           default_start=default_start, default_end=default_end)


@app.route('/salik/edit/<int:salik_id>', methods=['GET', 'POST'])
def edit_salik(salik_id: int):
    """Edit an existing Salik entry."""
    entry = Salik.query.get_or_404(salik_id)
    if request.method == 'POST':
        entry.start_date = datetime.strptime(request.form['start_date'], '%d/%m/%Y').date()
        entry.end_date = datetime.strptime(request.form['end_date'], '%d/%m/%Y').date()
        entry.amount = float(request.form['amount'])
        # Update payment status
        entry.paid = True if request.form.get('paid') == 'on' else False
        entry.settled_via = request.form.get('settled_via') or None
        db.session.commit()
        return redirect(url_for('list_rentals'))
    return render_template('edit_salik.html', entry=entry)


@app.route('/salik/delete/<int:salik_id>', methods=['POST'])
def delete_salik(salik_id: int):
    """Delete a Salik entry."""
    entry = Salik.query.get_or_404(salik_id)
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for('list_rentals'))


@app.route('/salik/rental/<int:rental_id>')
def list_salik_for_rental(rental_id: int):
    """List all Salik entries for a given rental."""
    rental = Rental.query.get_or_404(rental_id)
    entries = rental.salik_entries
    return render_template('salik_list.html', rental=rental, entries=entries)


# ---------------------------------------------------------------------------
# Reporting

@app.route('/reports')
def reports():
    """
    Generate utilisation and financial reports for each car. Utilisation is
    calculated as the total days a car has been rented compared to the
    duration from the earliest rental start to today (or 365 days if that
    period is shorter). Financials include total revenue from payments,
    total expenses (expenses + fines + damages), profit/loss and investment
    recovery progress.
    """
    today = date.today()
    report_rows = []
    cars = Car.query.all()
    for car in cars:
        # Gather rentals for this car
        car_rentals = car.rentals
        # Compute earliest start date
        start_dates = [r.start_date for r in car_rentals if r.start_date]
        if start_dates:
            earliest = min(start_dates)
        else:
            earliest = today
        # Utilisation days rented
        days_rented = 0
        for r in car_rentals:
            s = r.start_date
            if not s:
                continue
            e = r.end_date or today
            days_rented += (e - s).days + 1
        total_period = (today - earliest).days + 1
        if total_period < 1:
            total_period = 1
        utilisation_pct = round((days_rented / total_period) * 100, 2)
        # Revenue from payments
        payments = Payment.query.join(Rental).filter(Rental.car_id == car.id).all()
        total_revenue = sum(p.amount or 0 for p in payments)
        # Expenses: car expenses + fines + damages (cost to company)
        car_expenses = sum(e.cost or 0 for e in car.expenses)
        fines_cost = sum(f.amount or 0 for f in car.fines)
        damages_cost = sum(d.amount or 0 for d in car.damages)
        # Include Salik costs as part of expenses.  These represent toll charges paid by the company.
        salik_cost = sum(s.amount or 0 for s in car.salik)
        total_expenses = car_expenses + fines_cost + damages_cost + salik_cost
        # Purchase and initial investment
        purchase = car.purchase_price or 0
        investment = car.initial_investment or 0
        # Profit/loss
        profit_loss = total_revenue - total_expenses - purchase - investment
        # Investment recovery progress
        invested_total = purchase + investment
        if invested_total > 0:
            recovery_pct = round((total_revenue / invested_total) * 100, 2)
        else:
            recovery_pct = None
        report_rows.append({
            'car': car,
            'utilisation_pct': utilisation_pct,
            'days_rented': days_rented,
            'total_revenue': total_revenue,
            'total_expenses': total_expenses,
            'profit_loss': profit_loss,
            'recovery_pct': recovery_pct,
        })
    return render_template('reports.html', rows=report_rows, today=today)


def init_db():
    """Initialise the database tables."""
    db.create_all()
    print("Database initialised.")

# ---------------------------------------------------------------------------
# Helper functions

def date_in_range(d: date, start: date, end: date) -> bool:
    """Return True if date d falls between start and end inclusive."""
    return start <= d <= end


def is_rented_today(car: Car, today: date) -> bool:
    """Return True if the given car has an active rental overlapping today."""
    for r in car.rentals:
        if r.start_date and (r.end_date is None or r.end_date >= today):
            if r.start_date <= today:
                return True
    return False


def is_booked_today(car: Car, today: date) -> bool:
    """Return True if the given car has a booking that overlaps today but isn't rented."""
    for b in car.bookings:
        if date_in_range(today, b.start_date, b.end_date):
            return True
    return False


def rental_deposit_balance(rental: Rental) -> float:
    """
    Compute the remaining deposit balance for a rental by subtracting all
    fines and damages settled via deposit. Returns 0 if no deposit defined.
    """
    if not rental.deposit:
        return 0.0
    balance = rental.deposit
    # subtract fines settled via deposit for this rental's car and customer
    for f in rental.customer.fines:
        if f.car_id == rental.car_id and f.settled_via == 'deposit':
            balance -= f.amount or 0
    for d in rental.customer.damages:
        if d.car_id == rental.car_id and d.settled_via == 'deposit':
            balance -= d.amount or 0
    return max(balance, 0.0)


# ---------------------------------------------------------------------------
# Rental due summary

@app.route('/rental/due/<int:rental_id>')
def rental_due_summary(rental_id: int):
    """
    Display a summary of the amounts currently due for a rental.  The due
    calculation is based on the number of billing intervals that have elapsed
    since the rental start date, multiplied by the agreed rent, minus any
    payments already recorded.  Outstanding fines, damages and Salik costs
    associated with the rental's car and customer are added to the base
    amount.  Payments are not allocated to specific charges, but reduce
    the overall balance.

    If the rental has an end date before today, the calculation stops at
    the end date; otherwise it uses today's date.  Billing interval days
    are stored on the rental and default to 30.
    """
    rental = Rental.query.get_or_404(rental_id)
    today = date.today()
    # Determine the end of the billing period: either rental end date or today
    period_end = rental.end_date if rental.end_date and rental.end_date < today else today
    days_active = (period_end - rental.start_date).days
    # At least one interval has elapsed once the rental starts
    intervals = (days_active // (rental.billing_interval_days or 30)) + 1
    # Calculate base rent due
    rent_rate = rental.actual_rent if rental.actual_rent is not None else rental.planned_rent or 0.0
    base_due = rent_rate * intervals
    # Sum payments for this rental
    total_payments = sum(p.amount or 0 for p in rental.payments)
    # Outstanding fines and damages for this rental's car and customer
    outstanding_fines = [f for f in rental.customer.fines if f.car_id == rental.car_id and not f.paid]
    outstanding_damages = [d for d in rental.customer.damages if d.car_id == rental.car_id and not d.paid]
    # Outstanding Salik entries for this rental (unpaid)
    outstanding_salik = [s for s in rental.salik_entries if not getattr(s, 'paid', False)]
    charges_due = sum(f.amount or 0 for f in outstanding_fines) + \
                  sum(d.amount or 0 for d in outstanding_damages) + \
                  sum(s.amount or 0 for s in outstanding_salik)
    due_amount = base_due + charges_due - total_payments
    return render_template('rental_due.html', rental=rental,
                           base_due=base_due,
                           intervals=intervals,
                           charges_due=charges_due,
                           total_payments=total_payments,
                           due_amount=due_amount,
                           outstanding_fines=outstanding_fines,
                           outstanding_damages=outstanding_damages,
                           outstanding_salik=outstanding_salik,
                           period_end=period_end)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Car rental management app")
    parser.add_argument('--init-db', action='store_true', help='Initialise the database')
    args = parser.parse_args()
    if args.init_db:
        with app.app_context():
            init_db()
    else:
         app.run(debug=True)