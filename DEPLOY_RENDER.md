# Deploying to Render

This guide walks through deploying the Fundraising Prospect Engine webapp to Render, a cloud hosting platform.

## Prerequisites

1. **Render account** - Sign up at https://render.com (free tier available)
2. **GitHub repository** - Push this code to GitHub (Render deploys from Git)
3. **Environment variables** - Have your `PG_DSN` (PostgreSQL connection string) and `ANTHROPIC_API_KEY` ready
4. **PostgreSQL database** - Either use Render's managed PostgreSQL or an existing database

## Step 1: Push to GitHub

If you haven't already, initialize and push this repo to GitHub:

```bash
git remote add origin https://github.com/your-username/fundraising-leads-pipeline.git
git branch -M main
git push -u origin main
```

## Step 2: Create a PostgreSQL Database on Render

1. Log into [Render Dashboard](https://dashboard.render.com)
2. Click **New +** → **PostgreSQL**
3. Configure:
   - **Name**: `fundraising-db`
   - **Database**: `fundraising` (or your preferred name)
   - **User**: `fundraising_user` (will be auto-generated)
   - **Region**: Choose closest to your users (or same as web service)
   - **Plan**: `Standard` ($15/month) or `Free` (0.5GB, limited)
4. Click **Create Database**
5. Wait for it to initialize (2-3 minutes)
6. Copy the **Internal Database URL** (starts with `postgres://`)
   - This will be your `PG_DSN` environment variable

## Step 3: Apply Database Schema

Before deploying the web service, you need to load the schema:

1. In Render Dashboard, open your PostgreSQL database
2. Click **Connect** and copy the **psql** connection string
3. In your local terminal, connect and load the schema:
   ```bash
   psql "your-database-url" -f schema.sql
   ```
4. Run the migrations:
   ```bash
   psql "your-database-url" -f migrations/001_init.sql
   psql "your-database-url" -f migrations/002_frl_basis_virtual_status.sql
   psql "your-database-url" -f migrations/003_remove_routing.sql
   psql "your-database-url" -f migrations/004_state_ids.sql
   psql "your-database-url" -f migrations/005_scoring_source.sql
   psql "your-database-url" -f migrations/006_verification_queue.sql
   psql "your-database-url" -f migrations/007_crm_layer.sql
   psql "your-database-url" -f migrations/008_verification_queue_latest_score.sql
   psql "your-database-url" -f migrations/009_follow_up_signal_link.sql
   psql "your-database-url" -f migrations/010_daily_priority_due_date.sql
   ```

## Step 4: Deploy the Web Service

### Option A: Using Render Dashboard (Recommended for first-time)

1. Click **New +** → **Web Service**
2. Connect your GitHub repository:
   - Click **Connect GitHub Account** if prompted
   - Select your `fundraising-leads-pipeline` repo
   - Branch: `main`
3. Configure the service:
   - **Name**: `fundraising-webapp`
   - **Region**: Same as database (important for performance)
   - **Branch**: `main`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn webapp.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: `Standard` ($7/month) or `Free` (limited)
4. Add Environment Variables:
   - Click **Advanced** → **Add Environment Variable**
   - `PG_DSN`: Paste your PostgreSQL internal database URL from Step 2
   - `ANTHROPIC_API_KEY`: Paste your Anthropic API key
   - `LLM_MODEL`: `claude-opus-5`
   - `USER_AGENT`: `FundraisingProspectEngine/0.1`
   - `PYTHONUNBUFFERED`: `1`
5. Click **Create Web Service**
6. Wait for the initial deploy (3-5 minutes)

### Option B: Using render.yaml (for CI/CD pipelines)

1. In Render Dashboard, click **New +** → **Blueprint**
2. Select your GitHub repository
3. Render will auto-detect and use `render.yaml`
4. You'll still need to add secrets manually:
   - Go to **Render Dashboard** → **Settings** → **Secrets**
   - Add `ANTHROPIC_API_KEY`
5. Deploy using the blueprint

## Step 5: Verify Deployment

1. Once deployment completes, Render will assign a public URL (e.g., `https://fundraising-webapp.onrender.com`)
2. Visit the URL in your browser
3. You should see the home page with today's priority list

### Troubleshooting

**No data showing / 500 errors:**
- Check Render logs: Dashboard → Web Service → **Logs**
- Common issues:
  - `PG_DSN` is wrong or uses external URL instead of internal
  - Database schema not applied
  - Environment variables not set

**"Module not found" errors:**
- Check that all imports in `requirements.txt` match what's in the code
- Rebuild: Dashboard → Web Service → **Manual Deploy**

**Database connection timeouts:**
- Make sure database is in the same region as the web service
- Check that the database URL is the **Internal** URL, not the external one

## Step 6: Set Up Auto-Deploy

Render automatically redeploys when you push to the `main` branch. To disable:
- Dashboard → Web Service → **Settings** → Toggle **Auto-Deploy** off

## Monitoring & Maintenance

### Logs
- Render Dashboard → Web Service → **Logs**
- Watch for errors in real-time

### Environment Variables
- To update: Dashboard → Web Service → **Environment** → Edit
- Redeploy after changes

### Database Backups
- Enable auto-backups: Dashboard → PostgreSQL → **Backups**
- Manual backup: **Backups** → **Trigger Backup**

### Data Sync

The webapp reads from your PostgreSQL database, but doesn't run the ingest pipeline. To sync data:

1. **Option A: Run ingest locally**, then the database updates are visible in the webapp immediately
2. **Option B: Add a scheduled job to Render** (paid feature) to run ingest nightly
3. **Option C: Use external cron service** (e.g., cron-job.org) to call a webhook

For now, ingest runs locally and updates the shared database.

## Pricing

- **Web Service (Standard)**: $7/month
- **PostgreSQL (Standard)**: $15/month
- **Free tier**: Limited (0.5GB DB, limited compute) but good for testing

**Total estimate**: ~$22/month for production use

## Next Steps

1. ✅ Created `requirements.txt`, `Procfile`, `runtime.txt`, `render.yaml`
2. ✅ Created this deployment guide
3. 📝 TODO: Create a Render account and follow the steps above
4. 📝 TODO: Test the deployed app in production
5. 📝 TODO: (Optional) Set up monitoring and alerts

## Support

For issues:
- [Render Docs](https://render.com/docs)
- [Render Community](https://community.render.com)
- Check web service **Logs** tab for error messages
