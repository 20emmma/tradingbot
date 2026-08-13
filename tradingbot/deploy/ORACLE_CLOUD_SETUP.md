# Hosting on Oracle Cloud (Always Free Tier)

This gets you a small Linux server that runs 24/7 at $0/month, permanently
(not a trial). It's more setup than a paid provider, but worth it given
your trading capital is small.

## 1. Create an Oracle Cloud account

1. Go to oracle.com/cloud/free
2. Sign up (requires a credit card for identity verification, but the
   Always Free resources genuinely will not charge you — Oracle will not
   auto-upgrade you to paid without explicit action on your part)
3. Choose your home region during signup — pick one close to you, and
   note it down, since Always Free resources are tied to that region

## 2. Create the VM instance

1. In the Oracle Cloud Console, go to **Compute → Instances → Create Instance**
2. Name it (e.g. `tradingbot-server`)
3. Under **Image and shape**:
   - Image: **Ubuntu 22.04** (or latest LTS)
   - Shape: choose an **Always Free eligible** shape — either:
     - `VM.Standard.E2.1.Micro` (simpler, less powerful, totally fine for this bot), or
     - `VM.Standard.A1.Flex` (ARM-based, more resources, also free — slightly more setup nuance since it's ARM)
   - For this bot's workload (checking prices hourly, lightweight logic), the E2.1.Micro is plenty
4. Under **Networking**: leave defaults (it'll create a new VCN — virtual network)
5. Under **Add SSH keys**: choose "Generate a key pair for me" and **download both the public and private key** — you'll need the private key to connect
6. Click **Create**

Wait a minute or two for it to say "Running."

## 3. Connect to your server

On your own computer:

```bash
chmod 400 ~/Downloads/ssh-key-....key   # the private key you downloaded
ssh -i ~/Downloads/ssh-key-....key ubuntu@<YOUR_INSTANCE_PUBLIC_IP>
```

(Find the public IP on the instance's detail page in the Oracle Console.)

## 4. Set up the server

Once connected via SSH:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git -y
```

## 5. Deploy the bot code

If you push this project to a private GitHub repo:
```bash
git clone <your-repo-url> tradingbot
cd tradingbot
```

Or, simplest for now, transfer the files directly from your computer:
```bash
# Run this from YOUR computer, not the server:
scp -i ~/Downloads/ssh-key-....key -r ./tradingbot ubuntu@<YOUR_INSTANCE_IP>:~/tradingbot
```

Then on the server:
```bash
cd tradingbot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env    # fill in your real API keys and settings, save with Ctrl+O, exit with Ctrl+X
```

## 6. Open the firewall for the dashboard

Oracle's default security rules allow outbound traffic (needed to reach
Kraken/OANDA APIs) but block inbound traffic by default — good for
security. Since the dashboard is a web page you view in your browser,
we need to open one inbound port (5000) for it.

**In the Oracle Console:**
1. Go to your instance's detail page → find the attached **Virtual Cloud Network (VCN)** → click into it
2. Go to **Security Lists** → click the default security list
3. **Add Ingress Rule**:
   - Source CIDR: `0.0.0.0/0` (anywhere — fine for a read-only status dashboard, but see note below)
   - IP Protocol: TCP
   - Destination Port Range: `5000`
4. Save

**On the server itself**, Ubuntu's local firewall may also block it:
```bash
sudo ufw allow 5000/tcp
```

**Security note**: the dashboard is read-only (shows status, can't place
trades or change settings), so opening it publicly is low-risk — but if
you want it private, you can instead restrict the Source CIDR to just
your own home IP address, or leave it closed and use `ssh -L 5000:localhost:5000 ubuntu@<IP>`
to tunnel to it only when you want to check in.

Once open, visit `http://<YOUR_INSTANCE_IP>:5000` in your browser.

## 7. Test the bot manually first (before setting up auto-restart)

```bash
source venv/bin/activate
python3 main.py
```

Watch the logs for a minute or two — confirm it's fetching real prices
without errors. Ctrl+C to stop it once you've confirmed it's working.

## 8. Set it up as a permanent service

Follow `deploy/README.md` in this project (systemd setup) so it keeps
running after you disconnect.

## Common gotchas

- **"Out of capacity" error when creating the free VM**: Oracle's free
  tier is popular and sometimes has no free capacity in a given region.
  Try a different availability domain, or try again later — this is a
  known Oracle quirk, not something wrong with your account.
- **Can't SSH in**: double-check the key file permissions (`chmod 400`)
  and that you're using the exact public IP shown in the console.
- **pip install fails**: make sure you activated the virtual environment
  (`source venv/bin/activate`) first — you'll see `(venv)` in your prompt
  when it's active.
