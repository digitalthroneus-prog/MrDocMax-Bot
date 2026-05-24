#!/bin/bash
# MrDocMax Elite VPS Setup Script

echo "🔳 Initializing MrDocMax Elite Deployment..."

# 1. Install Dependencies
sudo apt-get update
sudo apt-get install -y python3-pip git supervisor

# 2. Setup Directory
sudo mkdir -p /opt/mrdocmax
sudo chown $USER:$USER /opt/mrdocmax
cd /opt/mrdocmax

# 3. Clone Repository
git clone https://github.com/digitalthroneus-prog/MrDocMax-Bot.git .

# 4. Install Python Requirements
pip3 install -r requirements.txt

# 5. Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file..."
    read -p "Enter TELEGRAM_BOT_TOKEN: " token
    read -p "Enter EMERGENT_API_KEY: " api_key
    echo "TELEGRAM_BOT_TOKEN=$token" > .env
    echo "EMERGENT_API_KEY=$api_key" >> .env
    echo "EMERGENT_API_BASE_URL=https://integrations.emergentagent.com/llm" >> .env
fi

# 6. Configure Supervisor
cat <<SVC | sudo tee /etc/supervisor/conf.d/mrdocmax.conf
[program:mrdocmax]
command=python3 main.py
directory=/opt/mrdocmax
autostart=true
autorestart=true
stderr_logfile=/var/log/mrdocmax.err.log
stdout_logfile=/var/log/mrdocmax.out.log
user=$USER
SVC

# 7. Start the bot
sudo supervisorctl update
sudo supervisorctl start mrdocmax

echo "✅ MRDOCMAX is now online 24/7."
