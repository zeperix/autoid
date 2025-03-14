#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
PLAIN='\033[0m'
BLUE="\033[36m"

echo "Vui lòng chọn ngôn ngữ | Please select a language"
echo -e "${YELLOW}Please note that the language you choose will affect the output of the backend program"
echo -e "Vui lòng lưu ý rằng ngôn ngữ bạn chọn sẽ ảnh hưởng đến đầu ra của chương trình backend${PLAIN}"
echo "1.Tiếng Việt(vi_vn)"
echo "2.English(en_us)"
read -e language
if [ $language != "1" ] && [ $language != "2" ] && [ $language != "3" ]; then
    echo "Lỗi nhập liệu, đã thoát | Input error, exit"
    exit;
fi
if [ $language == '1' ]; then
  echo "Quản lý Apple ID bằng cách mới, chương trình kiểm tra và giải mã Apple ID dựa trên câu hỏi bảo mật"
  echo "==============================================================="
else
  echo "Manage Apple ID in a new way, a program to check and decode Apple ID based on security questions"
  echo "==============================================================="
fi
if docker >/dev/null 2>&1; then
    echo "Docker đã được cài đặt | Docker is installed"
else
    echo "Docker chưa được cài đặt, bắt đầu cài đặt..."
    docker version > /dev/null || curl -fsSL get.docker.com | bash
    systemctl enable docker && systemctl restart docker
    echo "Docker đã được cài đặt | Docker installed"
fi
if [ $language == '1' ]; then
  echo "Bắt đầu cài đặt Apple_Auto backend"
  echo "Vui lòng nhập URL API (https://example.com)"
  read -e api_url
  echo "Vui lòng nhập API Key"
  read -e api_key
  echo "Bạn có muốn kích hoạt tự cập nhật không? (y/n)"
  read -e auto_update
  echo "Vui lòng nhập khoảng thời gian đồng bộ hóa (đơn vị: phút, mặc định 15)"
  read -e sync_time
  if [ "$sync_time" = "" ]; then
      sync_time=15
  fi
  echo "Bạn có muốn triển khai Selenium Docker container không? (y/n)"
  read -e run_webdriver
else
  echo "Start installing Apple_Auto backend"
  echo "Please enter API URL (https://example.com)"
  read -e api_url
  echo "Please enter API Key"
  read -e api_key
  echo "Do you want to enable auto-update? (y/n)"
  read -e auto_update
  echo "Please enter synchronization interval (unit: minutes, default 5)"
  read -e sync_time
  if [ "$sync_time" = "" ]; then
      sync_time=5
  fi
  echo "Do you want to deploy Selenium Docker container? (y/n)"
  read -e run_webdriver
fi
if [ "$run_webdriver" = "y" ]; then
    echo "Bắt đầu triển khai Selenium Docker container | Start deploying Selenium Docker container"
    echo "Vui lòng nhập cổng chạy Selenium (mặc định 4444)"
    read -e webdriver_port
    if [ "$webdriver_port" = "" ]; then
        webdriver_port=4444
    fi
    echo "Vui lòng nhập số lượng phiên làm việc tối đa (mặc định 10)"
    read -e webdriver_max_session
    if [ "$webdriver_max_session" = "" ]; then
        webdriver_max_session=10
    fi
    if docker ps -a --format '{{.Names}}' | grep -q '^webdriver$'; then
    docker rm -f webdriver
    fi
    docker pull selenium/standalone-chrome
    docker run -d --name=webdriver --log-opt max-size=1m --log-opt max-file=1 --shm-size="1g" --restart=always -e SE_NODE_MAX_SESSIONS=$webdriver_max_session -e SE_NODE_OVERRIDE_MAX_SESSIONS=true -e SE_SESSION_RETRY_INTERVAL=1 -e SE_START_VNC=false -p $webdriver_port:4444 selenium/standalone-chrome
    echo "Webdriver Docker container đã được triển khai | Webdriver Docker container deployed"
fi

# Set auto_update flag for command line
auto_update_flag=$([ "$auto_update" == "y" ] && echo "-auto_update" || echo "")

# Download and extract abc.zip
if [ $language == '1' ]; then
  echo "Tải xuống và giải nén tệp cần thiết..."
else
  echo "Downloading and extracting file..."
fi

wget -O /usr/local/bin/autoid https://raw.githubusercontent.com/zeperix/autoid/refs/heads/main/autoid
mkdir auto
cd auto
wget https://raw.githubusercontent.com/zeperix/autoid/refs/heads/main/main.py
wget https://raw.githubusercontent.com/zeperix/autoid/refs/heads/main/api.py
wget https://raw.githubusercontent.com/zeperix/autoid/refs/heads/main/lang.py
wget https://raw.githubusercontent.com/zeperix/autoid/refs/heads/main/requirements.txt

# Create systemd service for api.py
if [ $language == '1' ]; then
  echo "Tạo service để chạy dự án..."
else
  echo "Creating service to run project..."
fi

# Get current directory
CURRENT_DIR=$(pwd)

# Create service file
cat > /etc/systemd/system/appleauto.service << EOF
[Unit]
Description=Apple Auto Backend Service
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${CURRENT_DIR}
ExecStart=/usr/bin/python3 ${CURRENT_DIR}/api.py -api_url ${api_url} -api_key ${api_key} -lang=${language} ${auto_update_flag} -sync_time ${sync_time}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
systemctl daemon-reload
systemctl enable appleauto.service
systemctl start appleauto.service

if [ $language = "1" ]; then
  echo "Cài đặt hoàn tất, service đã khởi chạy"
  echo "Tên service: appleauto"
  echo "Cách sử dụng:"
  echo "Dừng service: systemctl stop appleauto"
  echo "Khởi động lại service: systemctl restart appleauto"
  echo "Xem log service: journalctl -u appleauto -f"
else
  echo "Installation completed, service started"
  echo "Service name: appleauto"
  echo "Operation method:"
  echo "Stop: systemctl stop appleauto"
  echo "Restart: systemctl restart appleauto"
  echo "Check logs: journalctl -u appleauto -f"
fi
exit 0