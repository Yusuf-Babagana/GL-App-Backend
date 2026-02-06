# Globalink Backend

The robust Django REST Framework (DRF) backend powering the Globalink Super App. This system manages e-commerce, logistics, secure financial transactions, and real-time messaging.

## 🚀 Features

### 1. **Marketplace & E-Commerce (`market`)**
- **Product Management**: Create, update, and delete products with image/video support.
- **Store System**: Users can open stores and manage inventory.
- **Order System**: Atomic Checkout with Escrow protection.
- **Escrow**: Funds are locked upon order and released only after delivery confirmation.

### 2. **Finance & Wallet (`finance`)**
- **Digital Wallet**: Every user has a wallet for transactions.
- **Monnify Integration**:
  - **Virtual Accounts**: Auto-generated bank accounts for easy top-ups.
  - **Withdrawals**: Secure transfers to real bank accounts.
- **VTPass Integration**:
  - **Bill Payments**: Buy Data and Airtime directly from the wallet.
- **Unified Logic**: Centralized `WalletManager` ensures race-condition-free transactions.

### 3. **Logistics & Delivery (`logistics`)**
- **Rider System**: Riders can view and accept "Ready for Pickup" jobs.
- **Secure Delivery**: 4-digit PIN verification required to mark items as delivered.
- **Auto-Hashes**: Delivery confirmation triggers automatic fund release.

### 4. **Real-Time Chat (`chat`)**
- **Messaging**: Buyer-Seller communication.
- **Polling**: Optimized message polling for real-time feel.
- **Push Notifications**: Expo Push integration for new message alerts.

### 5. **User Management (`users`)**
- **Authentication**: JWT (JSON Web Token) via `simplejwt`.
- **Roles**: Dynamic roles (Buyer, Seller, Rider, Admin).

---

## 🛠️ Tech Stack

- **Framework**: Django 5.x, Django REST Framework
- **Database**: SQLite (Dev) / PostgreSQL (Prod)
- **Authentication**: JWT (SimpleJWT)
- **Payments**: Monnify (Fiat), VTPass (Bills)
- **Deployment**: PythonAnywhere (via GitHub Actions)

---

## 📂 Project Structure

```text
GL-Backend/
├── .github/            # GitHub Actions (CI/CD)
├── chat/               # Real-time Messaging
├── finance/            # Wallet, Monnify, VTPass
├── globalink_core/     # Project Settings & Config
├── jobs/               # Job Board & Gigs
├── logistics/          # Delivery & Tracking
├── market/             # E-commerce, Products, Orders
├── users/              # Authentication & Profiles
├── media/              # Uploaded Content
├── static/             # Static Assets
├── .env                # Environment Variables
├── db.sqlite3          # Dev Database
├── manage.py           # Management Script
└── requirements.txt    # Dependencies
```

---

## ⚡ Getting Started

### Prerequisites
- Python 3.9+
- pip
- Git

### 1. Clone & Install
```bash
git clone https://github.com/your-repo/GL-Backend.git
cd GL-Backend

python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Environment Variables (.env)
Create a `.env` file in the root directory. You **MUST** add these keys:

```ini
DEBUG=True
SECRET_KEY=your_django_secret

# Database (Optional, defaults to SQLite)
# DB_NAME=...
# DB_USER=...

# Monnify (Fintech)
MONNIFY_API_KEY=MK_TEST_...
MONNIFY_SECRET_KEY=...
MONNIFY_CONTRACT_CODE=...
MONNIFY_BASE_URL=https://sandbox.monnify.com/api/v1

# VTPass (Bills)
VTPASS_API_KEY=...
VTPASS_SECRET_KEY=...
VTPASS_BASE_URL=https://sandbox.vtpass.com/api
```

### 3. Run Migrations & Server
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Access the API at: `http://127.0.0.1:8000/`

---

## 📡 Key API Endpoints

| Module | Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| **Auth** | POST | `/api/users/login/` | obtain JWT token |
| **Market** | GET | `/api/market/products/` | List all products |
| **Market** | POST | `/api/market/orders/create/` | Checkout (Escrow) |
| **Finance** | GET | `/api/finance/wallet/` | Check Balance & History |
| **Finance** | POST | `/api/finance/withdraw/` | Withdraw to Bank |
| **Bills** | POST | `/api/logistics/purchase-data/` | Buy mobile data |
| **Chat** | GET | `/api/chat/conversations/` | List chats |

---

## 🔄 Deployment

This project uses **GitHub Actions** for continuous deployment to PythonAnywhere.
- **Workflow**: `.github/workflows/deploy.yml`
- **Mechanism**: Triggers a `git pull` on the server and reloads the web app via API.

---

&copy; 2024 Globalink Team
