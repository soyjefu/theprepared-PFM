# Dockerfile for pfm-account_app

# 1. 베이스 이미지 설정 (Python 3.12 버전)
# 히스토리의 PYTHON_VERSION=3.12.11을 기반으로 유추
FROM python:3.12-slim

# 2. 환경 변수 설정 (Dockerfile에 명시되어 있지 않았지만, 추가하는 것이 일반적)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. 시스템 의존성 패키지 설치
# 히스토리에 apt-get install이 있었으므로 필요한 패키지를 여기에 추가
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# 5. Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 소스 코드 복사
COPY . /app

# 7. 앱 실행을 위한 유저 및 그룹 생성
RUN groupadd -r account-group && \
    useradd -r -g account-group account-user

# 8. 앱 디렉토리 권한 설정
RUN chown -R account-user:account-group /app

# 9. non-root 유저로 전환
USER account-user

# 10. 정적 파일 수집 (Django)
RUN python manage.py collectstatic --no-input

# 11. 컨테이너 실행 명령어
# 히스토리의 CMD ["gunicorn" "--bind" "0.0.0.0:8000" ... ]를 기반으로 재구성
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "the_project_name.wsgi:application"]