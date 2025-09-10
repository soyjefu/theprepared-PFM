# Debian 12 (Bookworm) 기반의 Python 3.12 slim 이미지를 사용
FROM python:3.12-slim-bookworm

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 의존성 설치 (PostgreSQL 클라이언트 라이브러리 및 빌드 도구)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 의존성 파일 복사 및 설치 (requirements.txt는 account-app 디렉토리에 있음)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Django 프로젝트 파일 복사
# account-app의 모든 내용을 /app으로 복사합니다.
# 이렇게 하면 /app 아래에 manage.py, theprepared_ac/, account/ 가 모두 들어갑니다.
COPY . /app

# --- 비루트 사용자 생성 및 권한 설정 시작 ---
# 'account-user'라는 이름의 새로운 사용자 및 그룹 생성
RUN groupadd -r account-group && useradd -r -g account-group account-user

# /app 디렉토리의 소유자를 새로 생성한 사용자로 변경
RUN chown -R account-user:account-group /app

# 컨테이너의 기본 사용자를 'account-user'로 설정
USER account-user
# --- 비루트 사용자 생성 및 권한 설정 끝 ---

# Django 정적 파일 수집
# 이 명령어는 애플리케이션 코드 복사 및 사용자 전환 후에 실행되어야 합니다.
# 비루트 사용자로 정적 파일을 수집하도록 합니다.
RUN python manage.py collectstatic --noinput

# Gunicorn을 사용하여 Django 애플리케이션 실행
# Gunicorn은 /app/theprepared_ac/wsgi.py를 참조합니다.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "theprepared_ac.wsgi:application"]