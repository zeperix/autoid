import argparse
import logging
import threading
import time
import os
import subprocess
from json import loads, dumps

import schedule
import urllib3
from flask import Flask, request
from requests import post

urllib3.disable_warnings()

prefix = "apple-auto_"
parser = argparse.ArgumentParser(description="")
parser.add_argument("-api_url", help="API URL", required=True)
parser.add_argument("-api_key", help="API key", required=True)
parser.add_argument("-sync_time", help="Khoảng thời gian đồng bộ hóa", default="10")
parser.add_argument('-lang', help='Language', default='1')
parser.add_argument("-auto_update", help="Bật cập nhật tự động", action='store_true')
args = parser.parse_args()

api_url = args.api_url
api_key = args.api_key
sync_time = int(args.sync_time)
enable_auto_update = args.auto_update

logger = logging.getLogger()
logger.setLevel('INFO')
BASIC_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(BASIC_FORMAT, DATE_FORMAT)
chlr = logging.StreamHandler()
chlr.setFormatter(formatter)
logger.addHandler(chlr)

if args.lang == '1':
    language = 'vi_vn'
elif args.lang == '2':
    language = 'en_us'
else:
    logger.error("Ngôn ngữ không hợp lệ, mặc định sử dụng tiếng Việt")
    language = 'vi_vn'

# Đường dẫn đến thư mục chứa các file service
SERVICE_DIR = "/etc/systemd/system"

# Lấy đường dẫn tuyệt đối của thư mục hiện tại
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

class API:
    def __init__(self):
        self.url = api_url
        self.key = api_key

    def get_backend_api(self):
        try:
            result = loads(
                post(f"{self.url}/api/get_backend_api",
                     verify=False,
                     headers={"key": self.key}).text)
        except Exception as e:
            logger.error("Lỗi khi lấy API")
            logger.error(e)
            return {'enable': False}
        else:
            if result['code'] == 200:
                return result['data']
            else:
                logger.error("Lỗi khi lấy API")
                logger.error(result['msg'])
                return {'enable': False}

    def get_task_list(self):
        try:
            result = loads(
                post(f"{self.url}/api/get_task_list",
                     verify=False,
                     headers={"key": self.key}).text)
        except Exception as e:
            logger.error("Lỗi khi lấy danh sách công việc")
            logger.error(e)
            return False
        else:
            if result['code'] == 200:
                return result['data']
            else:
                logger.error("Lỗi khi lấy danh sách công việc")
                logger.error(result['msg'])
                return None


class local_service:
    def __init__(self, api):
        self.api = api
        self.local_list = self.get_local_list()

    def deploy_service(self, id):
        try:
            service_name = f"{prefix}{id}"
            service_path = f"{SERVICE_DIR}/{service_name}.service"
            
            # Tạo nội dung file service
            service_content = f"""[Unit]
Description=AppleID Auto Service {id}
After=network.target

[Service]
Type=simple
WorkingDirectory={CURRENT_DIR}
ExecStart=/usr/bin/python3 {CURRENT_DIR}/main.py -api_url={self.api.url} -api_key={self.api.key} -taskid={id} -lang={language}
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""
            # Ghi file service
            with open(service_path, 'w') as f:
                f.write(service_content)
            
            # Reload systemd và enable+start service
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "enable", f"{service_name}.service"], check=True)
            subprocess.run(["systemctl", "start", f"{service_name}.service"], check=True)
            
        except Exception as e:
            logger.error(f"Lỗi khi triển khai dịch vụ {id}")
            logger.error(e)
        else:
            logger.info(f"Dịch vụ {id} đã được triển khai thành công")

    def remove_service(self, id):
        try:
            service_name = f"{prefix}{id}"
            
            # Stop và disable service
            subprocess.run(["systemctl", "stop", f"{service_name}.service"], check=True)
            subprocess.run(["systemctl", "disable", f"{service_name}.service"], check=True)
            
            # Xóa file service
            service_path = f"{SERVICE_DIR}/{service_name}.service"
            if os.path.exists(service_path):
                os.remove(service_path)
                
            # Reload systemd
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            
        except Exception as e:
            logger.error(f"Lỗi khi xóa dịch vụ {id}")
            logger.error(e)
        else:
            logger.info(f"Dịch vụ {id} đã được xóa thành công")

    def get_local_list(self):
        try:
            # Lấy danh sách các service đang chạy có prefix
            result = subprocess.run(["systemctl", "list-units", f"{prefix}*.service", "--no-legend"], 
                                   capture_output=True, text=True, check=True)
            
            local_list = []
            for line in result.stdout.splitlines():
                if line.strip():
                    service_name = line.split()[0].replace('.service', '')
                    service_id = int(service_name.replace(prefix, ""))
                    local_list.append(service_id)
                    
            logger.info(f"Có {len(local_list)} dịch vụ cục bộ")
            return local_list
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách dịch vụ cục bộ: {e}")
            return []

    def restart_service(self, id):
        try:
            if int(id) not in self.local_list:
                return self.sync()
            else:
                service_name = f"{prefix}{id}"
                subprocess.run(["systemctl", "restart", f"{service_name}.service"], check=True)
        except Exception as e:
            logger.error(f"Lỗi khi khởi động lại dịch vụ {id}")
            logger.error(e)
        else:
            logger.info(f"Dịch vụ {id} đã được khởi động lại thành công")

    def get_remote_list(self):
        result_list = self.api.get_task_list()
        if result_list is None or result_list is False:
            logger.info("Lỗi khi lấy danh sách công việc từ cloud, sử dụng danh sách cục bộ")
            return self.local_list
        else:
            logger.info(f"Đã lấy được {len(result_list)} công việc từ cloud")
            return result_list

    def sync(self):
        logger.info("Đang đồng bộ hóa")
        self.local_list = self.get_local_list()
        remote_list = self.get_remote_list()
        local_set = set(self.local_list)
        remote_set = set(remote_list)

        for id in local_set - remote_set:
            self.remove_service(id)
            self.local_list.remove(id)

        for id in remote_set - local_set:
            self.deploy_service(id)
            self.local_list.append(id)
        logger.info("Đã đồng bộ hóa")

    def clean_local_services(self):
        logger.info("Đang xóa dịch vụ cục bộ")
        self.local_list = self.get_local_list()
        for id in self.local_list:
            self.remove_service(id)
        logger.info("Đã xóa dịch vụ cục bộ")

    def update(self):
        logger.info("Đang kiểm tra cập nhật")
        # Kiểm tra cập nhật cho mã nguồn
        try:
            # Giả sử có một script cập nhật
            update_result = subprocess.run(["/www/wwwroot/back/update.sh"], check=True, capture_output=True)
            if "updated" in update_result.stdout.decode():
                logger.info("Đã phát hiện cập nhật")
                self.clean_local_services()
                self.sync()
                logger.info("Đã cập nhật")
            else:
                logger.info("Không có cập nhật")
        except Exception as e:
            logger.error(f"Lỗi khi kiểm tra cập nhật: {e}")


def job():
    global Local
    logger.info("Đang thực hiện nhiệm vụ định kỳ")
    Local.sync()


def update():
    global Local
    Local.update()


def start_app(ip, port, token):
    logging.info("Khởi chạy API")
    app = Flask(__name__)

    @app.before_request
    def before_request():
        # 检测请求类型是和否为POST
        if request.method != 'POST':
            logging.error("Loại yêu cầu không hợp lệ")
            data = {'status': False, 'msg': 'Loại yêu cầu không hợp lệ'}
            json_data = dumps(data).encode('utf-8')
            return app.response_class(json_data, mimetype='application/json')
        if 'token' not in request.headers:
            logging.error("Token không có trong phần đầu của yêu cầu")
            data = {'status': False, 'msg': 'Token không có trong phần đầu của yêu cầu'}
            json_data = dumps(data).encode('utf-8')
            return app.response_class(json_data, mimetype='application/json')
        if request.headers['token'] != token:
            logging.error("Mật khẩu không đúng")
            data = {'status': False, 'msg': 'Mật khẩu không đúng'}
            json_data = dumps(data).encode('utf-8')
            return app.response_class(json_data, mimetype='application/json')
        if 'id' not in request.form:
            logging.error("Không có ID công việc")
            data = {'status': False, 'msg': 'Không có ID công việc'}
            json_data = dumps(data).encode('utf-8')
            return app.response_class(json_data, mimetype='application/json')

    @app.route('/syncTask', methods=['POST'])
    def resync():
        logging.info("Nhận yêu cầu đồng bộ hóa công việc")
        thread_add_task = threading.Thread(target=Local.sync)
        thread_add_task.start()
        data = {'status': True, 'msg': 'Đồng bộ hóa thành công'}
        json_data = dumps(data).encode('utf-8')
        return app.response_class(json_data, mimetype='application/json')

    @app.route('/addTask', methods=['POST'])
    def add_task():
        logging.info("Nhận yêu cầu thiết lập công việc")
        thread_add_task = threading.Thread(target=Local.deploy_service, args=(request.form['id'],))
        thread_add_task.start()
        data = {'status': True, 'msg': 'Thiết lập thành công'}
        json_data = dumps(data).encode('utf-8')
        return app.response_class(json_data, mimetype='application/json')

    @app.route('/removeTask', methods=['POST'])
    def remove_task():
        logging.info("Nhận yêu cầu xóa công việc")
        thread_remove_task = threading.Thread(target=Local.remove_service, args=(request.form['id'],))
        thread_remove_task.start()
        data = {'status': True, 'msg': 'Xóa thành công'}
        json_data = dumps(data).encode('utf-8')
        return app.response_class(json_data, mimetype='application/json')

    @app.route('/restartTask', methods=['POST'])
    def restart_task():
        logging.info("Nhận yêu cầu khởi động lại công việc")
        thread_remove_task = threading.Thread(target=Local.restart_service, args=(request.form['id'],))
        thread_remove_task.start()
        data = {'status': True, 'msg': 'Khởi động lại thành công'}
        json_data = dumps(data).encode('utf-8')
        return app.response_class(json_data, mimetype='application/json')

    app.run(host=ip, port=port)


def remove_local_services():
    try:
        # Lấy danh sách tất cả các service có prefix
        result = subprocess.run(["systemctl", "list-units", f"{prefix}*.service", "--no-legend"], 
                               capture_output=True, text=True, check=True)
        
        for line in result.stdout.splitlines():
            if line.strip():
                service_name = line.split()[0].replace('.service', '')
                # Stop và disable service
                subprocess.run(["systemctl", "stop", service_name], check=True)
                subprocess.run(["systemctl", "disable", service_name], check=True)
                
                # Xóa file service
                service_path = f"{SERVICE_DIR}/{service_name}.service"
                if os.path.exists(service_path):
                    os.remove(service_path)
        
        # Reload systemd
        subprocess.run(["systemctl", "daemon-reload"], check=True)
    except Exception as e:
        logger.error(f"Lỗi khi xóa dịch vụ: {e}")


def main():
    logger.info("Khởi chạy dịch vụ quản lý AppleAuto")
    api = API()
    backend_api_result = api.get_backend_api()
    global Local
    Local = local_service(api)
    logger.info("Chuẩn bị môi trường dịch vụ")
    
    logger.info("Xóa tất cả dịch vụ cục bộ")
    remove_local_services()

    if backend_api_result is not None and backend_api_result['enable']:
        thread_app = threading.Thread(target=start_app, daemon=True, args=(
            backend_api_result['listen_ip'], backend_api_result['listen_port'], backend_api_result['token']))
        thread_app.start()
    job()
    logger.info(f"Khoảng thời gian đồng bộ hóa là {sync_time} phút")
    schedule.every(sync_time).minutes.do(job)
    if enable_auto_update:
        logger.info("Kích hoạt cập nhật tự động")
        schedule.every(8).hours.do(update)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
