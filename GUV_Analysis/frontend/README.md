# Frontend Documentation

This is the frontend application for the GUV Analysis Platform, built with Vue 3, TypeScript, and Element Plus.

## Setup

### Prerequisites
- Node.js 16+
- npm or yarn

### Installation

```bash
npm install
```

### Development

```bash
npm run dev
```

The application will be available at `http://localhost:5173`.

## Features

### Dashboard
- View task statistics and recent activity.

### Task Management
- **Task List**: View all tasks (Admin views all, Users view their own).
- **Create Task**: Upload ND2 files for analysis.
- **Task Details**: View analysis progress, parameters, and original filename.

### Task Queue
- **Live Queue**: Monitor active and queued tasks.
- **Queue Logs**: Real-time logs of queue execution (start/stop/wait times).
- **History**: View completed tasks.

### System Configuration
- **System Info**: Monitor server resources (CPU/RAM/Disk).
- **Config**: View system version (e.g., `GUV_Analysis_V1.1.2`) and manage settings (Admin only).

### User Management (Admin Only)
- Create, edit, and delete users.
- Reset passwords.

## Configuration

The API URL is configured in `src/api/http.ts`.
Default: `http://localhost:8000/api/v1`
