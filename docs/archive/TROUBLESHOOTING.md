# Troubleshooting Guide 🔧

Common issues and how to fix them.

## "ModuleNotFoundError: No module named 'app'"

**Problem:** You're trying to run the application from the wrong directory.

**Solution:** Make sure you're in the `backend` directory, NOT the `backend/app` directory!

```bash
# ❌ WRONG - Don't do this
cd running-shoe-deals/backend/app
python main.py  # This will fail!

# ✅ CORRECT - Do this instead
cd running-shoe-deals/backend
python run.py  # This works!
```

**Why?** Python needs to see the `app` folder as a package. When you're inside `app/`, Python can't find the package.

---

## "python: command not found"

**Problem:** Python is not installed or not in your PATH.

**Solution:**

**Option 1:** Try `python3` instead:
```bash
python3 run.py
```

**Option 2:** Install Python:
- **macOS:** `brew install python@3.11` or download from python.org
- **Windows:** Download from python.org and check "Add to PATH"
- **Linux:** `sudo apt install python3.11`

---

## "pip: command not found"

**Problem:** pip is not installed.

**Solution:** Try `pip3` or install it:
```bash
python -m ensurepip --upgrade
# or
python3 -m ensurepip --upgrade
```

---

## Virtual Environment Won't Activate (Windows)

**Problem:** PowerShell execution policy blocking activation.

**Solution:** Run PowerShell as Administrator and execute:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then try activating again:
```powershell
venv\Scripts\activate
```

---

## "Port 8000 already in use"

**Problem:** Another application is using port 8000.

**Solution 1:** Change the port in `.env`:
```bash
# Edit .env file
API_PORT=8001
```

**Solution 2:** Kill the process using port 8000:
```bash
# macOS/Linux
lsof -ti:8000 | xargs kill -9

# Windows (Command Prompt as Admin)
netstat -ano | findstr :8000
taskkill /PID <PID_NUMBER> /F
```

---

## "No module named 'fastapi'" (or other packages)

**Problem:** Virtual environment not activated or packages not installed.

**Solution:**

1. **Activate virtual environment:**
```bash
# macOS/Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt.

2. **Install packages:**
```bash
pip install -r requirements.txt
```

---

## Database Errors / Corrupt Database

**Problem:** Database file is corrupted or has schema issues.

**Solution:** Reset the database:
```bash
# Delete the database
rm shoe_deals.db  # macOS/Linux
del shoe_deals.db  # Windows

# Recreate it
python seed_data.py
```

**Warning:** This deletes all data!

---

## "Cannot find module 'dotenv'" or similar

**Problem:** Dependencies not installed.

**Solution:**
```bash
# Make sure venv is activated (you should see (venv) in prompt)
pip install -r requirements.txt
```

---

## Server Starts But Can't Access API

**Problem:** Server bound to wrong interface or firewall blocking.

**Solution 1:** Check you're accessing the right URL:
- Try: http://localhost:8000/docs
- Try: http://127.0.0.1:8000/docs

**Solution 2:** Check the server output for the actual URL:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## Import Errors After Adding New Code

**Problem:** Python can't find your new modules.

**Solution:** Make sure you have `__init__.py` files:
```bash
# Each directory needs an __init__.py
backend/app/__init__.py
backend/app/models/__init__.py
backend/app/routers/__init__.py
backend/app/scrapers/__init__.py
```

These can be empty files, they just tell Python the directory is a package.

---

## "Database is locked"

**Problem:** SQLite database is being accessed by another process.

**Solution:**
```bash
# Stop all running servers
# Press Ctrl+C in any terminals running the server

# If that doesn't work, restart your terminal
# Or reboot your computer as last resort
```

---

## Can't See Changes After Editing Code

**Problem:** Server not reloading or cached imports.

**Solution 1:** Make sure you started with reload enabled:
```bash
python run.py  # Has reload=True built in
```

**Solution 2:** Manually restart the server:
```bash
# Press Ctrl+C to stop
# Then start again
python run.py
```

**Solution 3:** Clear Python cache:
```bash
find . -type d -name __pycache__ -exec rm -r {} +  # macOS/Linux
# Restart server after
```

---

## Playwright Installation Issues

**Problem:** Playwright browser binaries not installed.

**Solution:**
```bash
# Install playwright browsers
playwright install
```

This downloads the browser binaries needed for scraping.

---

## Quick Diagnosis Checklist ✅

When something isn't working, check:

1. **Are you in the right directory?**
   ```bash
   pwd  # Should show: .../running-shoe-deals/backend
   ```

2. **Is the virtual environment activated?**
   ```bash
   # You should see (venv) in your prompt
   which python  # Should point to venv/bin/python
   ```

3. **Are packages installed?**
   ```bash
   pip list  # Should show fastapi, sqlalchemy, etc.
   ```

4. **Does the database exist?**
   ```bash
   ls shoe_deals.db  # Should exist
   ```

5. **Is the .env file present?**
   ```bash
   ls .env  # Should exist
   ```

---

## Still Having Issues?

### Check the error message carefully:

**"No module named 'X'"** → Package not installed or venv not activated
**"Address already in use"** → Port is taken, change it
**"Permission denied"** → File permissions or need admin rights
**"Cannot connect to database"** → Database file missing or corrupted

### Get more detailed errors:

```bash
# Run with debug mode
uvicorn app.main:app --reload --log-level debug
```

### Clean slate approach:

```bash
# 1. Delete everything
rm -rf venv shoe_deals.db

# 2. Start fresh
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python seed_data.py
python run.py
```

---

## Pro Tips 💡

1. **Always activate venv first** before running any commands
2. **Run from backend directory** not backend/app
3. **Check terminal output** for helpful error messages
4. **Use run.py** instead of trying to run main.py directly
5. **Keep terminal open** to see server logs

---

## Getting Help

If you're still stuck:

1. **Check the error message** - it usually tells you what's wrong
2. **Look at the server logs** - they show what's happening
3. **Try the Quick Diagnosis Checklist** above
4. **Google the exact error message** (usually helpful!)

---

Remember: Most issues are either:
- Wrong directory
- Virtual environment not activated
- Packages not installed

Fix these three things and 90% of issues go away! 🎉
