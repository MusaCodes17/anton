# Quick Start Guide 🚀

Get your Running Shoe Deal Finder up and running in 5 minutes!

## Prerequisites Check

Before starting, make sure you have:

```bash
# Check Python version (need 3.11+)
python --version
# or
python3 --version

# Check pip is installed
pip --version
```

If Python is not installed:
- **macOS**: `brew install python@3.11` or download from python.org
- **Windows**: Download from python.org
- **Linux**: `sudo apt install python3.11` (Ubuntu/Debian)

## Step-by-Step Setup

### 1. Navigate to Backend Directory

```bash
cd running-shoe-deals/backend
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

### 3. Activate Virtual Environment

**macOS/Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt.

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

This will take 1-2 minutes. You'll see packages being installed.

### 5. Create Environment File

```bash
cp .env.example .env
```

The defaults are fine for local development!

### 6. Initialize Database

```bash
python seed_data.py
```

This creates the database and adds:
- 7 Canadian retailers
- 12 running shoes

You should see:
```
✅ Database initialized
✅ Added retailer: The Last Hunt
✅ Added retailer: JD Sports Canada
... etc
```

### 7. Start the Server

```bash
# Make sure you're in the backend directory, NOT backend/app/
# You should be in: running-shoe-deals/backend/
python run.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

## Test It's Working

### Option 1: Visit the Docs
Open your browser to: http://localhost:8000/docs

You'll see the interactive API documentation!

### Option 2: Try an API Call

In a new terminal:
```bash
curl http://localhost:8000/api/shoes
```

You should see JSON with all the shoes!

### Option 3: Check Dashboard Stats

```bash
curl http://localhost:8000/api/dashboard/stats
```

## What You Have Now

✅ **Backend API running on port 8000**
✅ **SQLite database with sample data**
✅ **7 retailers configured**
✅ **12 shoes to track**
✅ **Interactive API documentation**

## Next: Explore the API

Go to http://localhost:8000/docs and try:

1. **GET /api/shoes** - See all tracked shoes
2. **POST /api/shoes** - Add a new shoe
3. **GET /api/retailers** - See all retailers
4. **GET /api/dashboard/stats** - See statistics

## Common Issues

### "python: command not found"
Try `python3` instead of `python`

### "Permission denied" on activation
**Windows:** Run PowerShell as Administrator and execute:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### "Port 8000 already in use"
Change port in `.env`:
```
API_PORT=8001
```

### "Module not found"
Make sure virtual environment is activated:
```bash
# You should see (venv) in your prompt
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows
```

## What's Next?

After the backend is running, we'll build:

1. **Web Scraper** - To actually find shoe prices
2. **React Frontend** - To view deals in a nice UI
3. **Scheduler** - To automatically check for deals

But for now, you have a working API to build on!

## Stop the Server

Press `Ctrl+C` in the terminal where the server is running.

## Restart Everything

```bash
# 1. Activate venv (if not activated)
source venv/bin/activate

# 2. Make sure you're in the backend directory
cd running-shoe-deals/backend

# 3. Start server
python run.py
```

That's it! You're ready to start building the scraper. 🎉
