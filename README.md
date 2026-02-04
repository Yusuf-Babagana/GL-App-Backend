# Globalink Backend

Globalink Backend is a robust API built with Django and Django REST Framework (DRF) to power the Globalink application. It provides comprehensive services for user management, e-commerce, job markets, logistics, and financial transactions.

## Table of Contents
- [Features](#features)
- [Technologies](#technologies)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Installation](#installation)
- [Running the Application](#running-the-application)

## Features

The backend is modularized into several key applications:

### 1. Users (`users`)
- **Authentication**: Secure JWT-based authentication (Login, Register, Refresh Token).
- **User Management**: Custom user model with role-based access control.
- **Profiles**: User profile management and KYC verification support.

### 2. Market (`market`)
- **E-commerce**: Full-featured marketplace backend.
- **Products**: Product listings, searching, and filtering.
- **Stores**: Vendor store management.
- **Categories**: Hierarchical category structure for products.

### 3. Finance (`finance`)
- **Wallet System**: Digital wallet for users.
- **Transactions**: History of deposits, withdrawals, and payments.
- **Payments**: Integration for processing payments (extendable).

### 4. Jobs (`jobs`)
- **Job Board**: Posting and managing job listings.
- **Applications**: Handling user applications for jobs.
- **Gig Economy**: Support for freelance/gig-based work interactions.

### 5. Logistics (`logistics`)
- **Delivery**: Management of shipping and delivery services.
- **Tracking**: Order tracking capabilities.

## Technologies

- **Language**: Python 3.x
- **Framework**: Django 5.x
- **API**: Django REST Framework (DRF)
- **Authentication**: `djangorestframework-simplejwt`
- **CORS**: `django-cors-headers`
- **Database**: SQLite (Default for development)
- **Image Processing**: Pillow

## Project Structure

```text
GL-Backend/
├── globalink_core/     # Project configuration (settings, urls, wsgi)
├── finance/            # Finance app (wallets, transactions)
├── jobs/               # Jobs app (listings, applications)
├── logistics/          # Logistics app (deliveries, tracking)
├── market/             # Market app (products, stores, orders)
├── users/              # Users app (auth, profiles)
├── media/              # User-uploaded content
│   ├── category_icons/
│   ├── product_images/
│   ├── store_logos/
│   └── kyc_docs/
├── db.sqlite3          # Development database
├── manage.py           # Django management script
└── requirements.txt    # Python dependencies
```

## Getting Started

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Virtualenv (recommended)

### Installation

1. **Clone the repository** (if applicable) or navigate to the project directory.

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**:
   - On Windows:
     ```bash
     venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Apply migrations**:
   ```bash
   python manage.py migrate
   ```

6. **Create a superuser** (for Admin panel access):
   ```bash
   python manage.py createsuperuser
   ```

### Running the Application

Start the development server:
```bash
python manage.py runserver
```

The API will be available at `http://127.0.0.1:8000/`.
Access the Admin interface at `http://127.0.0.1:8000/admin/`.

## API Endpoints

The API follows RESTful principles. Key endpoints include:

- **Auth**: `/api/users/login/`, `/api/users/register/` (Check `users/urls.py`)
- **Market**: `/api/market/products/`, `/api/market/stores/` (Check `market/urls.py`)
- **Jobs**: `/api/jobs/` (Check `jobs/urls.py`)
- **Finance**: `/api/finance/wallet/` (Check `finance/urls.py`)
- **Logistics**: `/api/logistics/` (Check `logistics/urls.py`)

---
Generated for Globalink Backend.
