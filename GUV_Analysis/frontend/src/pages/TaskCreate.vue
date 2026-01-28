<template>
  <div class="task-create">
    <h2>Create New Task</h2>

    <el-tabs v-model="uploadMode" :before-leave="beforeModeLeave" style="margin-top: 12px;">
      <el-tab-pane label="Queue Upload" name="queue">
        <el-card shadow="never">
          <el-alert
            v-if="hasQueueSession"
            :title="restoredQueueMessage || 'Queue session saved locally'"
            type="info"
            :closable="true"
            @close="restoredQueueMessage = ''"
            style="margin-bottom: 10px;"
          >
            <template #default>
              <div style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
                <el-button size="small" type="primary" @click="openReselectRemainingFiles" :disabled="queueRunning || uploading">Re-select Remaining Files</el-button>
                <el-button size="small" type="danger" @click="discardQueue" :disabled="queueRunning || uploading">Discard Queue</el-button>
                <span v-if="hasRestoredSession" style="opacity: 0.85;">Unfinished upload detected. Re-select files, then resume multipart if needed.</span>
              </div>
              <input ref="reselectRemainingInputEl" type="file" multiple accept=".nd2" style="display: none;" @change="handleReselectRemainingFiles" />
            </template>
          </el-alert>

          <el-form :model="queueConfig" label-width="120px" hide-required-asterisk>
            <el-form-item label="Batch Name">
              <el-input v-model="queueConfig.batchName" :disabled="queueRunning || uploading" placeholder="Optional prefix for task id & name" />
            </el-form-item>

            <el-form-item label="ND2 Files">
              <input type="file" multiple @change="handleQueueFileSelect" accept=".nd2" :disabled="queueRunning || uploading" />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" @click="startQueueUpload" :loading="queueRunning" :disabled="queueRunning || uploading || hasRestoredSession || queueItems.length === 0">Start Queue Upload</el-button>
              <el-button @click="stopQueue" :disabled="!queueRunning">Stop After Current</el-button>
              <el-button type="danger" @click="clearQueue" :disabled="queueRunning || uploading || queueItems.length === 0">Clear Queue</el-button>
            </el-form-item>
          </el-form>

          <div v-if="queueItems.length > 0" style="margin-top: 10px;">
            <el-table :data="queueItems" size="small" style="width: 100%;">
              <el-table-column label="#" width="60">
                <template #default="{ $index }">
                  <span>{{ $index + 1 }}</span>
                </template>
              </el-table-column>

              <el-table-column prop="fileName" label="File" min-width="220" />
              <el-table-column prop="fileSizeText" label="Size" width="120" />

              <el-table-column label="Task ID" min-width="220">
                <template #default="{ row }">
                  <el-input v-model="row.taskId" size="small" :disabled="queueRunning || uploading" @input="markQueueIdEdited(row)" />
                </template>
              </el-table-column>

              <el-table-column label="Task Name" min-width="260">
                <template #default="{ row }">
                  <el-input v-model="row.taskName" size="small" :disabled="queueRunning || uploading" @input="markQueueNameEdited(row)" />
                </template>
              </el-table-column>

              <el-table-column label="Status" width="120">
                <template #default="{ row }">
                  <el-tag :type="queueStatusTagType(row.status)">{{ queueStatusText(row.status) }}</el-tag>
                </template>
              </el-table-column>

              <el-table-column label="Task" width="120">
                <template #default="{ row }">
                  <router-link v-if="row.status === 'success'" :to="`/tasks/${row.taskId}`">View</router-link>
                  <span v-else>-</span>
                </template>
              </el-table-column>

              <el-table-column label="Actions" width="260">
                <template #default="{ row, $index }">
                  <el-button size="small" @click="regenerateQueueItemId(row)" :disabled="queueRunning || uploading">New ID</el-button>
                  <el-button size="small" @click="moveQueueItemUp($index)" :disabled="queueRunning || uploading || $index === 0">Up</el-button>
                  <el-button size="small" @click="moveQueueItemDown($index)" :disabled="queueRunning || uploading || $index === queueItems.length - 1">Down</el-button>
                  <el-button size="small" type="danger" @click="removeQueueItem($index)" :disabled="queueRunning || uploading">Remove</el-button>
                </template>
              </el-table-column>
            </el-table>

            <el-alert v-if="queueError" :title="queueError" type="error" :closable="true" @close="queueError = ''" style="margin-top: 10px;" />
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="Single Upload" name="single">
        <el-card shadow="never">
          <el-form :model="form" :rules="rules" ref="ruleFormRef" label-width="120px" hide-required-asterisk>
            <el-form-item label="Task ID" prop="id">
              <el-input v-model="form.id" placeholder="Start with letter, 4-32 chars, alphanumeric & underscore" :disabled="uploading || hasRestoredSession" />
            </el-form-item>

            <el-form-item label="Task Name" prop="name">
              <el-input v-model="form.name" :disabled="uploading || hasRestoredSession" />
            </el-form-item>
            
            <el-form-item label="ND2 File">
              <input type="file" @change="handleFileSelect" accept=".nd2" :disabled="uploading" />
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="onSubmit(ruleFormRef)" :loading="uploading" :disabled="uploading || hasRestoredSession">Create & Upload</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-alert
      v-if="hasRestoredSession"
      title="Unfinished upload session detected"
      type="warning"
      :closable="false"
      show-icon
      style="margin-top: 15px;"
    >
      <template #default>
        <div style="display: flex; flex-direction: column; gap: 10px;">
          <div style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
             <span>Task: <strong>{{ restoredSession?.taskId }}</strong> | File: <strong>{{ restoredSession?.fileName }}</strong></span>
             <el-button size="small" type="primary" @click="resumeRestoredMultipart" :disabled="!isResumeReady">Resume Multipart</el-button>
             <el-button size="small" type="danger" @click="discardUploadSession" :disabled="uploading">Discard</el-button>
          </div>
          <div v-if="!file || file.name !== restoredSession?.fileName" style="font-size: 0.9em; color: #E6A23C;">
             <el-icon><InfoFilled /></el-icon> Please re-select the file <strong>{{ restoredSession?.fileName }}</strong> below to enable the Resume button.
          </div>
          <div v-else style="font-size: 0.9em; color: #67C23A;">
             <el-icon><CircleCheckFilled /></el-icon> File matched. You can now resume the upload.
          </div>
        </div>
      </template>
    </el-alert>
    
    <div v-if="uploading || uploadLogs.length > 0" style="margin-top: 20px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
          <span v-if="uploading">Uploading... {{ progress }}%</span>
          <span v-else>Upload Process</span>
          
          <div style="display: flex; gap: 8px; align-items: center;">
            <el-button v-if="uploading && currentTaskId" size="small" type="warning" @click="pauseCurrentUpload">Pause</el-button>
            <el-button v-if="!uploading && currentTaskId && hasLocalActiveSession" size="small" type="primary" @click="resumeFromSessionCache" :disabled="!file">Resume</el-button>
            <el-button v-if="currentTaskId" size="small" type="danger" @click="abortCurrentUpload" :disabled="uploading">Terminate</el-button>
            <el-tag :type="statusBadgeType">{{ statusBadgeText }}</el-tag>
          </div>
      </div>
      <el-progress :percentage="progress" :status="uploadStatus" :show-text="false" />
      
      <div ref="terminalLogEl" class="terminal-log" style="background: #1e1e1e; color: #0f0; padding: 10px; margin-top: 10px; height: 300px; overflow-y: auto; font-family: 'Consolas', monospace; border-radius: 4px; border: 1px solid #333;">
        <pre style="white-space: pre-wrap; margin: 0;">{{ uploadLogsText }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import http from '@/api/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { InfoFilled, CircleCheckFilled } from '@element-plus/icons-vue'

const router = useRouter()
const uploadMode = ref<'queue' | 'single'>('queue')
const file = ref<File | null>(null)
const uploading = ref(false)
const progress = ref(0)
const uploadStatus = ref('') // 'success' | 'exception' | 'warning'
const uploadLogs = ref<string[]>([])
const ruleFormRef = ref<FormInstance>()

const UPLOAD_SESSION_KEY = 'guv.upload.session.v1'
const QUEUE_SESSION_KEY = 'guv.upload.queue.v1'
const MAX_LOG_LINES = 500

type QueueSessionItem = {
  taskId: string
  taskName: string
  fileName: string
  fileSize: number
  status: QueueItemStatus
  idEdited: boolean
  nameEdited: boolean
}

type QueueSession = {
  version: 1
  batchName: string
  cursor: number
  items: QueueSessionItem[]
}

type MultipartPart = { PartNumber: number; ETag: string }
type UploadSession = {
  version: 1
  taskId: string
  fileName: string
  fileSize: number
  startedAt: string
  mode: 'single' | 'multipart'
  uploading: boolean
  progress: number
  uploadStatus: string
  logs: string[]
  uploadId?: string
  chunkSize?: number
  parts?: MultipartPart[]
  uploadedBytes?: number
}

const currentTaskId = ref<string | null>(null)
const restoredSession = ref<UploadSession | null>(null)
const sessionCache = ref<UploadSession | null>(null)
const terminalLogEl = ref<HTMLElement | null>(null)
const uploadLogsText = computed(() => uploadLogs.value.join('\n'))
const paused = ref(false)
const hasLocalActiveSession = computed(() => {
  const s = sessionCache.value
  return !!s && s.mode === 'multipart' && !!s.uploadId && (s.uploadStatus || '') !== 'success'
})

type QueueItemStatus = 'pending' | 'uploading' | 'success' | 'failed' | 'skipped'
type QueueItem = {
  taskId: string
  taskName: string
  file: File | null
  fileName: string
  fileSize: number
  fileSizeText: string
  status: QueueItemStatus
  idEdited: boolean
  nameEdited: boolean
}

const queueConfig = reactive({
  batchName: '',
})

const queueItems = ref<QueueItem[]>([])
const queueRunning = ref(false)
const queueStopRequested = ref(false)
const queueError = ref('')
const queueCursor = ref(0)
const hasQueueSession = ref(false)
const restoredQueueMessage = ref('')
const reselectRemainingInputEl = ref<HTMLInputElement | null>(null)

const readQueueSession = (): QueueSession | null => {
  try {
    const raw = localStorage.getItem(QUEUE_SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || parsed.version !== 1 || !Array.isArray(parsed.items)) return null
    return parsed as QueueSession
  } catch {
    return null
  }
}

const writeQueueSession = (session: QueueSession | null) => {
  if (!session) {
    localStorage.removeItem(QUEUE_SESSION_KEY)
    hasQueueSession.value = false
    return
  }
  localStorage.setItem(QUEUE_SESSION_KEY, JSON.stringify(session))
  hasQueueSession.value = true
}

const snapshotQueueSession = () => {
  if (queueItems.value.length === 0) {
    writeQueueSession(null)
    return
  }
  const session: QueueSession = {
    version: 1,
    batchName: queueConfig.batchName || '',
    cursor: queueCursor.value,
    items: queueItems.value.map(i => ({
      taskId: i.taskId,
      taskName: i.taskName,
      fileName: i.fileName,
      fileSize: i.fileSize,
      status: i.status,
      idEdited: i.idEdited,
      nameEdited: i.nameEdited,
    })),
  }
  writeQueueSession(session)
}

const discardQueueSession = () => {
  restoredQueueMessage.value = ''
  queueCursor.value = 0
  writeQueueSession(null)
}

const discardQueue = () => {
  queueItems.value = []
  queueError.value = ''
  discardQueueSession()
}

const openReselectRemainingFiles = () => {
  const el = reselectRemainingInputEl.value
  if (!el) return
  el.value = ''
  el.click()
}

const handleReselectRemainingFiles = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (!target.files || target.files.length === 0) return
  const files = Array.from(target.files)

  const keyOf = (name: string, size: number) => `${name}::${size}`
  const map = new Map<string, File[]>()
  for (const f of files) {
    const k = keyOf(f.name, f.size)
    const arr = map.get(k)
    if (arr) arr.push(f)
    else map.set(k, [f])
  }

  let matched = 0
  const remaining = queueItems.value.filter(i => i.status !== 'success')
  for (const item of remaining) {
    if (item.file) continue
    const k = keyOf(item.fileName, item.fileSize)
    const arr = map.get(k)
    if (arr && arr.length > 0) {
      item.file = arr.shift() || null
      matched += 1
      if (arr.length === 0) map.delete(k)
    }
  }

  const rs = restoredSession.value
  if (rs) {
    const k = keyOf(rs.fileName, rs.fileSize)
    const matchedFile = files.find(f => keyOf(f.name, f.size) === k)
    if (matchedFile) file.value = matchedFile
  }

  const missing = remaining.filter(i => !i.file).map(i => i.fileName)
  queueCursor.value = Math.max(0, queueItems.value.findIndex(i => i.status !== 'success'))
  if (queueCursor.value < 0) queueCursor.value = 0
  snapshotQueueSession()

  if (matched > 0) {
    ElMessage.success(`Matched ${matched} file(s) to remaining queue items`)
  }
  if (missing.length > 0) {
    queueError.value = `Missing files: ${missing.join(', ')}`
    ElMessage.warning('Some remaining items are missing files. Please re-select them.')
  } else {
    queueError.value = ''
  }

  restoredQueueMessage.value = `Queue restored (${queueItems.value.length} items).`
  target.value = ''
}

const beforeModeLeave = () => {
  if (uploading.value || queueRunning.value) {
    ElMessage.warning('Upload is running. Please stop it before switching mode.')
    return false
  }
  return true
}

const restoreQueueFromSession = () => {
  const s = readQueueSession()
  if (!s) return
  uploadMode.value = 'queue'
  queueConfig.batchName = s.batchName || ''
  queueCursor.value = typeof s.cursor === 'number' ? s.cursor : 0
  queueItems.value = s.items.map(i => ({
    taskId: i.taskId,
    taskName: i.taskName,
    file: null,
    fileName: i.fileName,
    fileSize: i.fileSize,
    fileSizeText: formatBytes(i.fileSize),
    status: i.status,
    idEdited: !!i.idEdited,
    nameEdited: !!i.nameEdited,
  }))
  hasQueueSession.value = true
  restoredQueueMessage.value = `Queue restored (${queueItems.value.length} items). Please re-select remaining files to continue.`
}

const hasRestoredSession = computed(() => {
  const s = restoredSession.value
  if (!s) return false
  return s.uploadStatus !== 'success'
})

const canResumeMultipart = computed(() => {
  const s = restoredSession.value
  return !!s && s.mode === 'multipart' && !!s.uploadId && Array.isArray(s.parts)
})

const isResumeReady = computed(() => {
    if (!canResumeMultipart.value || uploading.value || !file.value) return false
    const s = restoredSession.value
    return s && file.value.name === s.fileName && file.value.size === s.fileSize
})

const readUploadSession = (): UploadSession | null => {
  try {
    const raw = localStorage.getItem(UPLOAD_SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || parsed.version !== 1 || !parsed.taskId) return null
    return parsed as UploadSession
  } catch {
    return null
  }
}

const writeUploadSession = (session: UploadSession | null) => {
  if (!session) {
    localStorage.removeItem(UPLOAD_SESSION_KEY)
    return
  }
  // Throttled write: only write if enough time passed or critical status change
  const now = Date.now()
  if (session.uploadStatus !== 'success' && session.uploadStatus !== 'exception' && !session.uploading) {
      // Always write if paused/stopped
      localStorage.setItem(UPLOAD_SESSION_KEY, JSON.stringify(session))
      lastSaveTime = now
      return
  }
  
  if (now - lastSaveTime > 2000) { // Save max once every 2 seconds
      localStorage.setItem(UPLOAD_SESSION_KEY, JSON.stringify(session))
      lastSaveTime = now
  }
}

let lastSaveTime = 0

const snapshotSession = (patch: Partial<UploadSession> = {}) => {
  const base: UploadSession | null = sessionCache.value
  const taskId = patch.taskId ?? currentTaskId.value ?? base?.taskId
  if (!taskId) return

  const next: UploadSession = {
    version: 1,
    taskId,
    fileName: patch.fileName ?? base?.fileName ?? (file.value?.name ?? ''),
    fileSize: patch.fileSize ?? base?.fileSize ?? (file.value?.size ?? 0),
    startedAt: patch.startedAt ?? base?.startedAt ?? new Date().toISOString(),
    mode: patch.mode ?? base?.mode ?? 'single',
    uploading: patch.uploading ?? uploading.value,
    progress: patch.progress ?? progress.value,
    uploadStatus: patch.uploadStatus ?? uploadStatus.value,
    logs: (patch.logs ?? uploadLogs.value).slice(-MAX_LOG_LINES),
    uploadId: patch.uploadId ?? base?.uploadId,
    chunkSize: patch.chunkSize ?? base?.chunkSize,
    parts: patch.parts ?? base?.parts,
    uploadedBytes: patch.uploadedBytes ?? base?.uploadedBytes,
  }

  sessionCache.value = next
  writeUploadSession(next)
}

const discardUploadSession = () => {
  restoredSession.value = null
  currentTaskId.value = null
  sessionCache.value = null
  writeUploadSession(null)
  uploadLogs.value = []
  progress.value = 0
  uploadStatus.value = ''
}

const statusBadgeType = computed(() => {
    if (uploadStatus.value === 'success') return 'success'
    if (uploadStatus.value === 'exception') return 'danger'
    if (uploading.value) return 'primary'
    return 'info'
})

const statusBadgeText = computed(() => {
    if (uploadStatus.value === 'success') return 'Complete'
    if (uploadStatus.value === 'exception') return 'Failed'
    if (paused.value) return 'Paused'
    if (uploading.value) return 'Uploading'
    return 'Waiting'
})

let scrollScheduled = false
const scheduleAutoScroll = () => {
  if (scrollScheduled) return
  scrollScheduled = true
  requestAnimationFrame(() => {
    scrollScheduled = false
    const el = terminalLogEl.value
    if (!el) return
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    if (distanceToBottom <= 40) {
      el.scrollTop = el.scrollHeight
    }
  })
}

const log = (msg: string) => {
    const timestamp = new Date().toLocaleTimeString()
    uploadLogs.value.push(`[${timestamp}] ${msg}`)
    if (uploadLogs.value.length > MAX_LOG_LINES) {
        uploadLogs.value.splice(0, uploadLogs.value.length - MAX_LOG_LINES)
    }
    snapshotSession({ logs: uploadLogs.value })
    nextTick(() => scheduleAutoScroll())
}

const form = reactive({
  id: '',
  name: '',
})

const rules = reactive<FormRules>({
  id: [
    { required: true, message: 'Please input Task ID', trigger: 'blur' },
    { 
      pattern: /^[a-zA-Z][a-zA-Z0-9_]{3,31}$/, 
      message: 'Task ID format error: Must start with letter, 4-32 chars, alphanumeric & underscore', 
      trigger: ['blur', 'change'] 
    }
  ],
  name: [
    { required: true, message: 'Please input Task Name', trigger: 'blur' }
  ]
})

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    const selectedFile = target.files[0]
    
    // Validation
    if (!selectedFile.name.toLowerCase().endsWith('.nd2')) {
        ElMessage.error('Only .nd2 files are allowed')
        target.value = '' // Clear selection
        file.value = null
        return
    }
    
    // 5GB limit warning (optional)
    if (selectedFile.size > 5 * 1024 * 1024 * 1024) {
        ElMessage.warning('File is larger than 5GB, upload may take a while')
    }
    
    file.value = selectedFile
  }
}

const formatBytes = (bytes: number) => {
  const KB = 1024
  const MB = 1024 * KB
  const GB = 1024 * MB
  if (bytes >= GB) return `${(bytes / GB).toFixed(2)} GB`
  if (bytes >= MB) return `${(bytes / MB).toFixed(2)} MB`
  if (bytes >= KB) return `${(bytes / KB).toFixed(2)} KB`
  return `${bytes} B`
}

const fileStem = (name: string) => {
  const lastSlash = Math.max(name.lastIndexOf('/'), name.lastIndexOf('\\'))
  const base = lastSlash >= 0 ? name.slice(lastSlash + 1) : name
  const dot = base.lastIndexOf('.')
  if (dot <= 0) return base
  return base.slice(0, dot)
}

const pad2 = (n: number) => String(n).padStart(2, '0')

const generateTaskId = () => {
  const d = new Date()
  const y = d.getFullYear()
  const m = pad2(d.getMonth() + 1)
  const day = pad2(d.getDate())
  const hh = pad2(d.getHours())
  const mm = pad2(d.getMinutes())
  const ss = pad2(d.getSeconds())
  const rand = Math.random().toString(16).slice(2, 6).padEnd(4, '0')
  return `t${y}${m}${day}_${hh}${mm}${ss}_${rand}`
}

const sanitizeBatchPrefix = () => {
  const raw = (queueConfig.batchName || '').trim()
  if (!raw) return 't'
  let s = raw.replace(/\s+/g, '_').replace(/[^a-zA-Z0-9_]/g, '_').replace(/_+/g, '_').replace(/^_+|_+$/g, '')
  if (!s) return 't'
  if (!/^[a-zA-Z]/.test(s)) s = `b_${s}`
  return s
}

const buildQueueTaskId = (index: number) => {
  const d = new Date()
  const yy = String(d.getFullYear()).slice(-2)
  const m = pad2(d.getMonth() + 1)
  const day = pad2(d.getDate())
  const hh = pad2(d.getHours())
  const mm = pad2(d.getMinutes())
  const ss = pad2(d.getSeconds())
  const dateTime = `${yy}${m}${day}${hh}${mm}${ss}`
  const idx = String(index)
  const rand = Math.random().toString(16).slice(2, 6).padEnd(4, '0')

  const fixedLen = 1 + idx.length + 1 + dateTime.length + 1 + rand.length
  const maxPrefixLen = Math.max(1, 32 - fixedLen)
  const prefix = sanitizeBatchPrefix().slice(0, maxPrefixLen)
  return `${prefix}_${idx}_${dateTime}_${rand}`
}

const buildQueueTaskName = (stem: string, index: number, total: number, used: Set<string>) => {
  const prefix = (queueConfig.batchName || '').trim()
  const base = prefix ? `${prefix} - ${index}/${total} - ${stem}` : stem
  let name = base
  let suffix = 2
  while (used.has(name)) {
    name = `${base} (${suffix})`
    suffix += 1
  }
  used.add(name)
  return name
}

const refreshQueueDerivedFields = () => {
  const usedNames = new Set<string>()
  const usedIds = new Set<string>()
  const total = queueItems.value.length
  for (let i = 0; i < queueItems.value.length; i++) {
    const item = queueItems.value[i]

    if (item.idEdited) {
      item.taskId = (item.taskId || '').trim()
      if (item.taskId) usedIds.add(item.taskId)
    } else {
      let nextId = buildQueueTaskId(i + 1)
      while (usedIds.has(nextId)) {
        nextId = buildQueueTaskId(i + 1)
      }
      item.taskId = nextId
      usedIds.add(nextId)
    }

    if (item.nameEdited) {
      const candidate = (item.taskName || '').trim() || fileStem(item.fileName)
      let final = candidate
      let suffix = 2
      while (usedNames.has(final)) {
        final = `${candidate} (${suffix})`
        suffix += 1
      }
      usedNames.add(final)
      item.taskName = final
      continue
    }
    const stem = fileStem(item.fileName)
    item.taskName = buildQueueTaskName(stem, i + 1, total, usedNames)
  }
}

watch(() => queueConfig.batchName, () => {
  if (queueRunning.value || uploading.value) return
  refreshQueueDerivedFields()
  snapshotQueueSession()
})

const handleQueueFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (!target.files || target.files.length === 0) return
  const files = Array.from(target.files)
  const newItems: QueueItem[] = []
  for (const f of files) {
    if (!f.name.toLowerCase().endsWith('.nd2')) {
      ElMessage.error('Only .nd2 files are allowed')
      continue
    }
    if (f.size > 5 * 1024 * 1024 * 1024) {
      ElMessage.warning('File is larger than 5GB, upload may take a while')
    }
    newItems.push({
      taskId: generateTaskId(),
      taskName: fileStem(f.name),
      file: f,
      fileName: f.name,
      fileSize: f.size,
      fileSizeText: formatBytes(f.size),
      status: 'pending',
      idEdited: false,
      nameEdited: false,
    })
  }
  if (newItems.length > 0) {
    queueItems.value = [...queueItems.value, ...newItems]
    refreshQueueDerivedFields()
    snapshotQueueSession()
  }
  target.value = ''
}

const markQueueNameEdited = (row: QueueItem) => {
  row.nameEdited = true
  snapshotQueueSession()
}

const markQueueIdEdited = (row: QueueItem) => {
  row.idEdited = true
  snapshotQueueSession()
}

const regenerateQueueItemId = (row: QueueItem) => {
  const idx = queueItems.value.indexOf(row)
  const used = new Set(queueItems.value.filter(i => i !== row).map(i => (i.taskId || '').trim()).filter(Boolean))
  let nextId = idx >= 0 ? buildQueueTaskId(idx + 1) : generateTaskId()
  while (used.has(nextId)) {
    nextId = idx >= 0 ? buildQueueTaskId(idx + 1) : generateTaskId()
  }
  row.taskId = nextId
  row.idEdited = true
  snapshotQueueSession()
}

const removeQueueItem = (index: number) => {
  queueItems.value.splice(index, 1)
  refreshQueueDerivedFields()
  snapshotQueueSession()
}

const moveQueueItemUp = (index: number) => {
  if (index <= 0) return
  const arr = queueItems.value
  const tmp = arr[index - 1]
  arr[index - 1] = arr[index]
  arr[index] = tmp
  refreshQueueDerivedFields()
  snapshotQueueSession()
}

const moveQueueItemDown = (index: number) => {
  const arr = queueItems.value
  if (index < 0 || index >= arr.length - 1) return
  const tmp = arr[index + 1]
  arr[index + 1] = arr[index]
  arr[index] = tmp
  refreshQueueDerivedFields()
  snapshotQueueSession()
}

const clearQueue = () => {
  discardQueue()
}

const stopQueue = () => {
  queueStopRequested.value = true
}

const queueStatusTagType = (status: QueueItemStatus) => {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'uploading') return 'primary'
  if (status === 'skipped') return 'warning'
  return 'info'
}

const queueStatusText = (status: QueueItemStatus) => {
  if (status === 'success') return 'Done'
  if (status === 'failed') return 'Failed'
  if (status === 'uploading') return 'Uploading'
  if (status === 'skipped') return 'Skipped'
  return 'Waiting'
}

const beforeUnloadHandler = (e: BeforeUnloadEvent) => {
  if (!uploading.value) return
  e.preventDefault()
  e.returnValue = ''
}

onMounted(() => {
  const s = readUploadSession()
  if (s) {
    restoredSession.value = s
    currentTaskId.value = s.taskId
    uploadLogs.value = Array.isArray(s.logs) ? s.logs : []
    progress.value = typeof s.progress === 'number' ? s.progress : 0
    uploadStatus.value = s.uploadStatus || ''
    sessionCache.value = s
    paused.value = false
  }
  const qs = readQueueSession()
  if (qs) {
    restoreQueueFromSession()
  }
  window.addEventListener('beforeunload', beforeUnloadHandler)
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', beforeUnloadHandler)
})

onBeforeRouteLeave(async () => {
  if (!uploading.value) return true
  try {
    await ElMessageBox.confirm(
      'An upload is in progress. Leaving this page may hide progress or interrupt the upload.',
      'Upload in progress',
      {
        confirmButtonText: 'Leave',
        cancelButtonText: 'Stay',
        type: 'warning',
      }
    )
    return true
  } catch {
    return false
  }
})

const resumeRestoredMultipart = async () => {
  const s = restoredSession.value
  if (!s) return
  if (!canResumeMultipart.value) {
    ElMessage.error('This session cannot be resumed (missing multipart info)')
    return
  }
  if (!file.value) {
    ElMessage.warning('Please select the same file to resume')
    return
  }
  if (file.value.name !== s.fileName || file.value.size !== s.fileSize) {
    ElMessage.error(`Selected file does not match previous upload: ${s.fileName} (${s.fileSize} bytes)`) 
    return
  }

  currentTaskId.value = s.taskId
  uploading.value = true
  uploadStatus.value = ''
  log(`Resuming upload for task: ${s.taskId}`)

  try {
    startStatusPoll(s.taskId)
    await uploadMultipart(s.taskId, file.value, s)
    log('Verifying upload with backend...')
    await http.post(`/tasks/${s.taskId}/upload/complete`)
    log('Upload verified successfully.')

    uploadStatus.value = 'success'
    snapshotSession({ uploadStatus: 'success', uploading: false, progress: 100 })
    writeUploadSession(null)
    restoredSession.value = null

    ElMessage.success('Upload completed')
    const shouldContinueQueue = uploadMode.value === 'queue' && (hasQueueSession.value || queueItems.value.length > 0)
    if (shouldContinueQueue) {
      const idx = queueItems.value.findIndex(i => i.taskId === s.taskId)
      if (idx >= 0) {
        queueItems.value[idx].status = 'success'
      }
      queueCursor.value = Math.max(0, queueItems.value.findIndex(i => i.status !== 'success'))
      if (queueCursor.value < 0) queueCursor.value = 0
      snapshotQueueSession()

      const missing = queueItems.value.filter(i => i.status !== 'success' && !i.file).map(i => i.fileName)
      if (missing.length > 0) {
        queueError.value = `Missing files: ${missing.join(', ')}`
        ElMessage.warning('Please re-select remaining files before continuing the queue.')
        return
      }
      setTimeout(() => {
        startQueueUpload()
      }, 300)
      return
    }

    setTimeout(() => {
      router.push(`/tasks/${s.taskId}`)
    }, 800)
  } catch (e: any) {
    if (e?.code === 'UploadPaused') {
      uploadStatus.value = 'warning'
      snapshotSession({ uploading: false })
      ElMessage.warning('Upload paused')
      return
    }
    uploadStatus.value = 'exception'
    const detailObj = parseBackendDetail(e)
    const errorMsg = detailObj?.message || (typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : '') || e?.message || 'Upload failed'
    log(`ERROR: ${errorMsg}`)
    snapshotSession({ uploadStatus: 'exception', uploading: false })
    ElMessage.error(errorMsg)
  } finally {
    uploading.value = false
    stopStatusPoll()
    snapshotSession({ uploading: false })
  }
}

class UploadPausedError extends Error {
  code = 'UploadPaused'
}

class UploadRestartRequiredError extends Error {
  code = 'NoSuchUpload'
}

const parseBackendDetail = (e: any) => {
  const detail = e?.response?.data?.detail
  if (detail && typeof detail === 'object') return detail
  return null
}

const isNoSuchUpload = (e: any) => {
  const detail = parseBackendDetail(e)
  return e?.response?.status === 409 && detail?.code === 'NoSuchUpload'
}

const isPausedOnServer = (e: any) => {
  const detail = parseBackendDetail(e)
  return e?.response?.status === 409 && detail?.code === 'UploadPaused'
}

const fetchUploadStatus = async (taskId: string) => {
  try {
    const { data } = await http.get(`/tasks/${taskId}/upload/status`, { timeout: 8000 })
    if (typeof data?.progress === 'number' && data.progress > progress.value) progress.value = data.progress
    paused.value = !!data?.paused
  } catch {
  }
}

let statusTimer: number | null = null
const startStatusPoll = (taskId: string) => {
  stopStatusPoll()
  statusTimer = window.setInterval(() => fetchUploadStatus(taskId), 2000)
}

const stopStatusPoll = () => {
  if (statusTimer) {
    window.clearInterval(statusTimer)
    statusTimer = null
  }
}

onUnmounted(() => {
  stopStatusPoll()
})

const pauseCurrentUpload = async () => {
  const taskId = currentTaskId.value
  if (!taskId) return
  try {
    await http.post(`/tasks/${taskId}/upload/pause`)
    paused.value = true
    log('Upload paused.')
    snapshotSession({ uploading: false })
  } catch (e: any) {
    log(`ERROR: ${e?.response?.data?.detail?.message || e?.message || 'Pause failed'}`)
  }
}

const abortCurrentUpload = async () => {
  const taskId = currentTaskId.value
  if (!taskId) return
  try {
    const s = sessionCache.value
    await http.post(`/tasks/${taskId}/multipart/proxy/abort`, { upload_id: s?.uploadId || '' })
    log('Upload terminated.')
    discardUploadSession()
  } catch (e: any) {
    log(`ERROR: ${e?.response?.data?.detail?.message || e?.message || 'Terminate failed'}`)
  }
}

const resumeFromSessionCache = async () => {
  const s = sessionCache.value
  if (!s || !file.value) return
  restoredSession.value = s
  await resumeRestoredMultipart()
}

const ensureMinioHealthy = async () => {
  log('Checking storage health...')
  const { data: health } = await http.get('/system/minio/health', { timeout: 10000 })
  if (!health?.ok) {
    const endpoint = health?.endpoint ? ` endpoint=${health.endpoint}` : ''
    const presignErr = health?.checks?.presign_put?.error ? ` presign_put=${health.checks.presign_put.error}` : ''
    const bucketErr = health?.checks?.bucket_exists?.error ? ` bucket_exists=${health.checks.bucket_exists.error}` : ''
    throw new Error(`MinIO unhealthy.${endpoint}${presignErr}${bucketErr}`.trim())
  }
  log('Storage is healthy.')
}

const createTaskEntry = async (taskId: string, taskName: string, f: File) => {
  log(`Creating task entry: ${taskId}`)
  const { data } = await http.post(
    '/tasks/',
    {
      id: taskId,
      name: taskName,
      filename: f.name,
      size: f.size,
    },
    { timeout: 30000 }
  )
  const { task_id, presigned_put_url } = data
  log(`Task created. ID: ${task_id}`)
  return { taskId: task_id as string, presignedPutUrl: presigned_put_url as string }
}

const uploadAndComplete = async (taskId: string, f: File, presignedPutUrl: string, navigateOnSuccess: boolean) => {
  currentTaskId.value = taskId
  const mode: 'single' | 'multipart' = 'multipart'
  snapshotSession({
    taskId,
    fileName: f.name,
    fileSize: f.size,
    startedAt: new Date().toISOString(),
    mode,
    uploading: true,
    progress: 0,
    uploadStatus: '',
    logs: uploadLogs.value,
  })

  if (presignedPutUrl) {
    try {
      await minioDirectPutProbe(presignedPutUrl)
      log('MinIO direct PUT probe: OK (browser restrictions likely lifted).')
    } catch (e: any) {
      log('MinIO direct PUT probe: FAILED (likely browser CORS/mixed-content restriction).')
    }
  }

  if (mode === 'multipart') {
    log(`File size ${f.size} > 100MB. Using Multipart Upload.`)
    startStatusPoll(taskId)
    await uploadMultipart(taskId, f, null)
  } else {
    log(`File size ${f.size} <= 100MB. Using Single PUT.`)
    await uploadWithRetry(presignedPutUrl, f)
  }

  log('Verifying upload with backend...')
  await http.post(`/tasks/${taskId}/upload/complete`)
  log('Upload verified successfully.')

  uploadStatus.value = 'success'
  snapshotSession({ uploadStatus: 'success', uploading: false, progress: 100 })
  writeUploadSession(null)
  ElMessage.success('Upload completed')
  if (navigateOnSuccess) {
    setTimeout(() => {
      router.push(`/tasks/${taskId}`)
    }, 1000)
  }
}

const runSingleTaskFlow = async (taskId: string, taskName: string, f: File, navigateOnSuccess: boolean) => {
  uploading.value = true
  progress.value = 0
  uploadStatus.value = ''
  uploadLogs.value = []
  currentTaskId.value = null
  writeUploadSession(null)
  restoredSession.value = null
  queueError.value = ''
  log('Starting task creation process...')

  await ensureMinioHealthy()
  const created = await createTaskEntry(taskId, taskName, f)
  await uploadAndComplete(created.taskId, f, created.presignedPutUrl, navigateOnSuccess)
}

const TASK_ID_PATTERN = /^[a-zA-Z][a-zA-Z0-9_]{3,31}$/

const validateQueueBeforeStart = () => {
  const used = new Set<string>()
  for (let i = 0; i < queueItems.value.length; i++) {
    const item = queueItems.value[i]
    const id = (item.taskId || '').trim()
    const name = (item.taskName || '').trim()
    if (item.status !== 'success' && !item.file) return { ok: false, message: `Queue item ${i + 1}: File is required (please re-select remaining files)` }
    if (!id) return { ok: false, message: `Queue item ${i + 1}: Task ID is required` }
    if (!TASK_ID_PATTERN.test(id)) return { ok: false, message: `Queue item ${i + 1}: Task ID format invalid` }
    if (used.has(id)) return { ok: false, message: `Queue item ${i + 1}: Duplicate Task ID: ${id}` }
    if (!name) return { ok: false, message: `Queue item ${i + 1}: Task Name is required` }
    used.add(id)
    item.taskId = id
    item.taskName = name
  }
  return { ok: true as const }
}

const startQueueUpload = async () => {
  if (queueRunning.value) return
  if (hasRestoredSession.value) {
    ElMessage.warning('There is an unfinished upload session. Please resume or discard it first.')
    return
  }
  if (queueItems.value.length === 0) {
    ElMessage.warning('Please add files to the queue')
    return
  }

  refreshQueueDerivedFields()
  const validation = validateQueueBeforeStart()
  if (!validation.ok) {
    queueError.value = validation.message
    ElMessage.error(validation.message)
    return
  }

  queueRunning.value = true
  queueStopRequested.value = false
  queueError.value = ''
  queueCursor.value = Math.max(0, queueItems.value.findIndex(i => i.status !== 'success'))
  if (queueCursor.value < 0) queueCursor.value = 0
  snapshotQueueSession()

  for (let idx = queueCursor.value; idx < queueItems.value.length; idx++) {
    if (queueStopRequested.value) break
    queueCursor.value = idx
    const item = queueItems.value[idx]
    if (item.status === 'success') continue
    item.status = 'uploading'
    snapshotQueueSession()
    try {
      if (!item.file) throw new Error('Missing file for this queue item')
      await runSingleTaskFlow(item.taskId, item.taskName, item.file, false)
      item.status = 'success'
      snapshotQueueSession()
    } catch (e: any) {
      if (e?.code === 'UploadPaused') {
        item.status = 'pending'
        snapshotQueueSession()
        break
      }
      item.status = 'failed'
      const detailObj = parseBackendDetail(e)
      const errorMsg = detailObj?.message || (typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : '') || e?.message || 'Upload failed'
      queueError.value = `Queue stopped at ${item.fileName}: ${errorMsg}`
      snapshotQueueSession()
      break
    } finally {
      uploading.value = false
      stopStatusPoll()
      snapshotSession({ uploading: false })
    }
  }

  queueRunning.value = false
  queueStopRequested.value = false
  queueCursor.value = Math.max(0, queueItems.value.findIndex(i => i.status !== 'success'))
  if (queueCursor.value < 0) queueCursor.value = 0
  if (queueItems.value.length > 0 && queueItems.value.every(i => i.status === 'success')) {
    discardQueueSession()
  } else {
    snapshotQueueSession()
  }
}

const onSubmit = async (formEl: FormInstance | undefined) => {
  if (!formEl) return
  
  await formEl.validate(async (valid, fields) => {
    if (valid) {
        if (!file.value) {
            ElMessage.warning('Please select a file')
            return
        }

        if (hasRestoredSession.value) {
            ElMessage.warning('There is an unfinished upload session. Please resume or discard it first.')
            return
        }

        try {
            await runSingleTaskFlow(form.id, form.name, file.value, true)
            
        } catch (e: any) {
            console.error(e)
            if (e?.code === 'UploadPaused') {
                uploadStatus.value = 'warning'
                snapshotSession({ uploading: false })
                return
            }
            uploadStatus.value = 'exception'
            let errorMsg = 'Upload failed'
            const detailObj = parseBackendDetail(e)
            if (detailObj?.message) {
                 errorMsg = detailObj.message
            } else if (e.response && e.response.data && typeof e.response.data.detail === 'string') {
                 errorMsg = e.response.data.detail
            } else {
                 errorMsg = e.message || 'Upload failed'
            }
            log(`ERROR: ${errorMsg}`)
            snapshotSession({ uploadStatus: 'exception', uploading: false })
            ElMessage.error(errorMsg)
        } finally {
            uploading.value = false
            stopStatusPoll()
            snapshotSession({ uploading: false })
        }
    } else {
        console.log('error submit!', fields)
    }
  })
}

// --- Single PUT ---
async function uploadWithRetry(url: string, file: File, retries = 3) {
    for (let i = 0; i < retries; i++) {
        try {
            log(`Starting upload attempt ${i + 1}/${retries}...`)
            await uploadToMinio(url, file)
            return
        } catch (e) {
            log(`Upload attempt ${i + 1} failed: ${e}`)
            console.warn(`Upload attempt ${i + 1} failed`, e)
            if (i === retries - 1) throw e
            // Wait 1s before retry
            log('Waiting 1s before retry...')
            await new Promise(r => setTimeout(r, 1000))
        }
    }
}

async function uploadToMinio(url: string, file: File) {
    return new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('PUT', url, true)
        xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream')
        xhr.timeout = 5 * 60 * 60 * 1000 // 5 hours
        
        let lastProgress = -1
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const p = Math.round((e.loaded / e.total) * 100)
                if (p !== lastProgress) {
                    progress.value = p
                    lastProgress = p
                    snapshotSession({ progress: p })
                }
            }
        }
        
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                resolve()
            } else {
                reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`))
            }
        }
        
        xhr.onerror = () => reject(new Error('Network Error'))
        xhr.ontimeout = () => reject(new Error('Connection Timeout'))
        
        xhr.send(file)
    })
}

async function minioDirectPutProbe(url: string) {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 8000)
    try {
        const resp = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/octet-stream' },
            body: new Uint8Array([0x61]),
            signal: controller.signal,
        })
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`)
        }
    } finally {
        window.clearTimeout(timeoutId)
    }
}

// --- Multipart Upload ---

function calculateUploadedBytes(parts: MultipartPart[], fileSize: number, chunkSize: number) {
    let sum = 0
    for (const p of parts) {
        const start = (p.PartNumber - 1) * chunkSize
        const end = Math.min(start + chunkSize, fileSize)
        if (end > start) sum += (end - start)
    }
    return sum
}

async function uploadMultipart(taskId: string, file: File, resumeSession: UploadSession | null = null) {
    let uploadId = resumeSession?.uploadId || ''
    const MB = 1024 * 1024
    const computeChunkSize = (fileSize: number) => {
        const min = 64 * MB
        const max = 256 * MB
        const round = 8 * MB
        const targetParts = 900
        let chunk = Math.ceil(fileSize / targetParts)
        chunk = Math.ceil(chunk / round) * round
        chunk = Math.max(min, Math.min(max, chunk))
        const parts = Math.ceil(fileSize / chunk)
        if (parts > 10000) {
            chunk = Math.ceil(fileSize / 9999)
            chunk = Math.ceil(chunk / round) * round
        }
        return chunk
    }

    const CHUNK_SIZE = resumeSession?.chunkSize || computeChunkSize(file.size)
    let parts: MultipartPart[] = Array.isArray(resumeSession?.parts) ? [...(resumeSession!.parts as MultipartPart[])] : []
    let uploadedBytes = typeof resumeSession?.uploadedBytes === 'number'
        ? (resumeSession!.uploadedBytes as number)
        : calculateUploadedBytes(parts, file.size, CHUNK_SIZE)

    const totalParts = Math.ceil(file.size / CHUNK_SIZE)

    await http.post(`/tasks/${taskId}/upload/resume`).catch(() => {})
    paused.value = false

    let restarted = false

    while (true) {
        if (uploadId) {
            try {
                const { data } = await http.get(`/tasks/${taskId}/multipart/proxy/status`, { params: { upload_id: uploadId }, timeout: 15000 })
                const serverParts: MultipartPart[] = Array.isArray(data?.parts) ? data.parts : []
                parts = serverParts
                uploadedBytes = calculateUploadedBytes(parts, file.size, CHUNK_SIZE)
                snapshotSession({ mode: 'multipart', uploadId, chunkSize: CHUNK_SIZE, parts, uploadedBytes })
            } catch (e: any) {
                if (isNoSuchUpload(e)) {
                    uploadId = ''
                    parts = []
                    uploadedBytes = 0
                } else {
                    throw e
                }
            }
        }

        if (!uploadId) {
            log('Initializing multipart upload (Proxy)...')
            const { data } = await http.post(`/tasks/${taskId}/multipart/proxy/init`, {
                chunk_size: CHUNK_SIZE,
                total_parts: totalParts,
                file_size: file.size,
            })
            uploadId = data.upload_id
            parts = []
            uploadedBytes = 0
            log(`Multipart initiated. UploadId: ${uploadId}`)
            snapshotSession({ mode: 'multipart', uploadId, chunkSize: CHUNK_SIZE, parts, uploadedBytes })
        } else {
            log(`Resuming multipart upload. UploadId: ${uploadId}`)
        }

        const maxUploadedPart = parts.length ? Math.max(...parts.map(p => p.PartNumber)) : 0
        const startPart = maxUploadedPart + 1

        log(`Using chunk size ${(CHUNK_SIZE / MB).toFixed(0)} MB. Total parts: ${totalParts}.`)
        log(`Starting upload of ${totalParts} parts...`)

        try {
            for (let partNumber = startPart; partNumber <= totalParts; partNumber++) {
                if (paused.value) throw new UploadPausedError('Upload paused')
                const start = (partNumber - 1) * CHUNK_SIZE
                const end = Math.min(start + CHUNK_SIZE, file.size)
                const chunk = file.slice(start, end)
                
                const shouldLog = partNumber === 1 || partNumber % 10 === 0 || partNumber === totalParts
                
                let etag = ''
                for (let attempt = 0; attempt < 3; attempt++) {
                    try {
                        if (attempt > 0 && shouldLog) log(`Retry ${attempt} for Part ${partNumber}...`)
                        const { data } = await http.put(
                            `/tasks/${taskId}/multipart/proxy/part`, 
                            chunk,
                            {
                                params: {
                                    upload_id: uploadId,
                                    part_number: partNumber
                                },
                                headers: {
                                    'Content-Type': 'application/octet-stream'
                                },
                                timeout: 2 * 60 * 60 * 1000 
                            }
                        )
                        etag = (data.ETag || '').replace(/"/g, '')
                        if (shouldLog) {
                            const pct = Math.round(((uploadedBytes + chunk.size) / file.size) * 100)
                            log(`Part ${partNumber}/${totalParts} uploaded. Progress ${pct}%`)
                        }
                        break
                    } catch (e: any) {
                        if (isNoSuchUpload(e)) throw new UploadRestartRequiredError('NoSuchUpload')
                        if (isPausedOnServer(e)) throw new UploadPausedError('Upload paused')
                        const isTimeout = e.code === 'ECONNABORTED' || e.message?.includes('timeout')
                        log(`Error uploading Part ${partNumber} (Attempt ${attempt+1}): ${isTimeout ? 'Timeout' : e.message}`)
                        console.error(e)
                        if (attempt === 2) throw e
                        await new Promise(r => setTimeout(r, 1000))
                    }
                }
                
                parts.push({ PartNumber: partNumber, ETag: etag })
                uploadedBytes += chunk.size
                progress.value = Math.round((uploadedBytes / file.size) * 100)
                snapshotSession({ parts, uploadedBytes, progress: progress.value })
            }
        } catch (e: any) {
            if (e?.code === 'UploadPaused') {
                snapshotSession({ uploading: false })
                throw e
            }
            if ((e?.code === 'NoSuchUpload' || e instanceof UploadRestartRequiredError) && !restarted) {
                restarted = true
                log('UploadId invalid (NoSuchUpload). Re-initializing and restarting upload from Part 1.')
                await http.post(`/tasks/${taskId}/multipart/proxy/abort`, { upload_id: uploadId }).catch(() => {})
                uploadId = ''
                parts = []
                uploadedBytes = 0
                continue
            }
            throw e
        }
        
        log('All parts uploaded. Completing multipart upload (Proxy)...')
        
        await http.post(`/tasks/${taskId}/multipart/proxy/complete`, {
            upload_id: uploadId,
            parts: parts
        })

        progress.value = 100
        snapshotSession({ progress: 100, parts, uploadedBytes })
        log('Multipart upload completed successfully.')
        break
    }
}
</script>
