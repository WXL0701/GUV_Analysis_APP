# Development Documentation

## Overview

The GUV Analysis Platform has been enhanced with several new modules:
1.  **Task Queue System**: Priority-based task execution with dependency management.
2.  **Multi-User System**: Role-Based Access Control (RBAC), User Management, and Messaging.
3.  **System Monitoring**: Real-time server resource usage, history, and alerting.
4.  **System Configuration**: Dynamic configuration management.

## Backend Architecture

### Tech Stack
-   **Framework**: FastAPI
-   **Database**: PostgreSQL (via SQLAlchemy)
-   **Task Queue**: Celery + Redis
-   **Storage**: MinIO

### New Modules

#### Task Queue (`app/api/routes/tasks.py`, `app/services/queue_service.py`)
-   **Service**: `QueueService` handles centralized task submission and status tracking.
-   **Mechanism**: FIFO (First-In-First-Out) execution using Celery with concurrency=1.
-   **Endpoints**:
    -   `GET /tasks/queue/status`: Returns real-time queue metrics (queued, running, total_active).
    -   `GET /tasks/queue/logs`: Returns recent queue execution logs.
    -   `GET /tasks/stats`: Returns historical statistics.
    -   `GET /tasks`: Supports filtering by `active`, `history`, `all`.
    -   `PUT /tasks/{id}/priority`: Update task priority.
-   **Models**: `Task` model updated with `priority`, `dependencies`, `progress`, `queue_position`.
-   **Flow**:
    1.  User submits task -> `QueueService.submit_task`.
    2.  Task status -> `QUEUED`.
    3.  Celery Worker picks task -> `RUNNING`.
    4.  Completion -> `SUCCEEDED` / `FAILED`.

#### Multi-User System (`app/api/routes/auth.py`, `users.py`)
-   **Authentication**: JWT-based auth (`/auth/login`, `/auth/register`).
-   **RBAC**: Users have roles (`admin`, `user`). `deps.get_current_admin_user` dependency enforces admin access.

#### System Monitoring (`app/api/routes/system.py`)
-   **Stats Collection**: Background thread collects CPU/RAM/Disk usage every minute and stores in `system_stats` table.
-   **Alerts**: Checks thresholds (configurable) and sends system messages to logs.
-   **Config**: `app_configs` table stores dynamic settings (`system.cpu_threshold`, etc.).
-   **Endpoints**:
    -   `GET /system/stats`: Returns current system resource usage.
    -   `GET /system/version`: Returns system version (from pipeline root).
    -   `GET /system/config`: List all configs (Admin only).
    -   `PUT /system/config/{key}`: Update config (Admin only).

### Database Migrations
-   New tables: `system_stats`, `app_configs`, `messages`.
-   Updated tables: `users` (added `role`), `tasks` (added queue fields).
-   Migration script: `migrate_v1.py` (Manual SQL migration for existing DB).

## Frontend Architecture

### Tech Stack
-   **Framework**: Vue 3 + TypeScript
-   **UI Library**: Element Plus
-   **Charts**: ECharts
-   **State Management**: Vue Composition API (refs/reactive)

### New Pages

#### Dashboard (`Dashboard.vue`)
-   Overview of task statistics using ECharts.
-   Quick access to recent tasks.

#### Task Queue (`TaskQueue.vue`)
-   **Live Queue**: Shows Active/Queued tasks with priority editing.
-   **Queue Logs**: Real-time display of queue execution logs (start/stop/wait times).
-   **History**: Searchable history of completed tasks.
-   **Visuals**: Queue statistics cards and activity chart.

#### User Management (`Users.vue`)
-   Admin-only page.
-   List, Create, Edit, Delete users.
-   Reset passwords.

#### System Info (`SystemInfo.vue`, `SystemConfig.vue`)
-   **Info**: Real-time gauges for CPU/RAM/Disk + Historical Line Charts.
-   **Config**: CRUD interface for system settings.

#### Messaging (`Messages.vue`)
-   Inbox/Outbox for user messages.
-   Compose new messages to other users.

#### Login/Register (`Login.vue`)
-   Unified login/register card.
-   Registration includes password checks:
    -   Minimum 8 characters.
    -   Must contain only letters (case-insensitive) and numbers.
    -   No special characters allowed.

#### Admin System
-   **Admin Account**: Default `Admin` / `12345678`.
-   **Permissions**: Admin can view all tasks (all users' history) and manage users. Regular users can only see their own tasks.
-   **Audit**: Admin actions (viewing global task lists, deleting user tasks) are logged.

## Setup & Running

### Prerequisites
-   Python 3.9+
-   Node.js 16+
-   PostgreSQL
-   Redis
-   MinIO

### Backend
```bash
cd backend
pip install -r requirements.txt
# Run migration if updating from v1.0
python migrate_v1.py
# Start Server
uvicorn app.main:app --reload
# Start Worker
celery -A app.worker.celery_app worker --loglevel=info -P solo
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Testing

### Backend Tests
Located in `backend/tests/`.
Run with:
```bash
pytest
```
Covers:
-   Task API & Stats
-   System Stats & Config
-   User Authentication (mocked)

## Configuration

Environment variables in `.env`:
-   `DATABASE_URL`
-   `REDIS_URL`
-   `MINIO_*`
-   `SECRET_KEY`

System-level configurations (thresholds, etc.) can be managed via the **System Config** page in the UI.
