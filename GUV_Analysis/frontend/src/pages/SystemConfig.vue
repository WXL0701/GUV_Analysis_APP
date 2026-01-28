<template>
  <div class="system-config-container">
    <el-card style="margin-bottom: 20px;">
      <template #header>
        <div class="card-header">
          <span>MATLAB Environment</span>
        </div>
      </template>
      <el-form label-width="140px">
        <el-form-item label="MATLAB Version">
          <el-select 
            v-model="currentMatlabVersion" 
            placeholder="Select MATLAB Version"
            style="width: 100%; max-width: 600px;"
            @change="handleMatlabVersionChange"
          >
            <el-option label="MATLAB R2018a (/usr/local/MATLAB/R2018a)" value="R2018a" />
            <el-option label="MATLAB R2024a (/usr/local/MATLAB/R2024a)" value="R2024a" />
          </el-select>
        </el-form-item>
        <el-form-item label="Package Version">
          <el-select 
            v-model="currentPipelineRoot" 
            placeholder="Select MATLAB Package" 
            style="width: 100%; max-width: 600px;"
            @change="handlePipelineRootChange"
            filterable
            allow-create
            default-first-option
          >
            <el-option 
              v-for="opt in pipelineOptions" 
              :key="opt.value" 
              :label="opt.label" 
              :value="opt.value" 
            />
          </el-select>
          <div style="margin-top: 8px; color: #606266; font-size: 13px;">
            <el-tag size="small" type="success" v-if="version">Detected: {{ version }}</el-tag>
            <div style="margin-top: 5px; word-break: break-all; line-height: 1.5; font-family: monospace; background: #f5f7fa; padding: 4px; border-radius: 4px;">Path: {{ currentPipelineRoot || 'Default' }}</div>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <template #header>
        <div class="card-header">
          <span>System Configuration</span>
          <div class="header-actions">
            <el-tag type="info" class="version-tag">Version: {{ version }}</el-tag>
            <el-button type="primary" @click="dialogVisible = true">
              <el-icon><Plus /></el-icon> Add Config
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="configs" style="width: 100%" v-loading="loading">
        <el-table-column prop="key" label="Key" width="200" sortable />
        <el-table-column prop="value" label="Value" min-width="200" />
        <el-table-column prop="description" label="Description" min-width="200" />
        <el-table-column label="Actions" width="150" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="handleEdit(scope.row)">Edit</el-button>
            <el-button link type="danger" @click="handleDelete(scope.row)">Delete</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? 'Edit Config' : 'Add Config'"
      width="500px"
    >
      <el-form :model="form" label-width="100px">
        <el-form-item label="Key" required>
          <el-input v-model="form.key" :disabled="isEdit" placeholder="e.g. system.alert_threshold" />
        </el-form-item>
        <el-form-item label="Value" required>
          <el-input v-model="form.value" type="textarea" placeholder="Configuration value" />
        </el-form-item>
        <el-form-item label="Description">
          <el-input v-model="form.description" placeholder="Optional description" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">Cancel</el-button>
          <el-button type="primary" @click="saveConfig" :loading="submitting">
            Confirm
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import http from '@/api/http'
import { ElMessage, ElMessageBox } from 'element-plus'

interface AppConfig {
  key: string
  value: string
  description?: string
}

const configs = ref<AppConfig[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const submitting = ref(false)
const isEdit = ref(false)
const version = ref('Loading...')
const currentPipelineRoot = ref('')
const currentMatlabVersion = ref('R2018a')
const pipelineOptions = ref<{label: string, value: string}[]>([])

const form = ref<AppConfig>({
  key: '',
  value: '',
  description: ''
})

const fetchPipelines = async () => {
  try {
    const res = await http.get('/system/pipelines')
    pipelineOptions.value = res.data.map((p: any) => ({
      label: `${p.name} ${p.is_valid ? '' : '(Invalid)'}`,
      value: p.path
    }))
  } catch (e) {
    console.error('Failed to fetch pipelines', e)
  }
}

const fetchVersion = async () => {
  try {
    const res = await http.get('/system/version')
    version.value = res.data.version
    if (res.data.pipeline_root) {
      currentPipelineRoot.value = res.data.pipeline_root
    }
    // Also fetch current matlab version config if possible, 
    // but usually we rely on fetchConfigs or a specific endpoint. 
    // For now, let's assume fetchConfigs populates it or we default to R2018a.
    // Actually, we should check configs for system.matlab_version
  } catch (e) {
    console.error(e)
    version.value = 'Unknown'
  }
}

const handleMatlabVersionChange = async (val: string) => {
  try {
    await http.post('/system/config', {
      key: 'system.matlab_version',
      value: val,
      description: 'MATLAB Runtime Version'
    }).catch(async (e) => {
       if (e.response && e.response.status === 400) {
          await http.put('/system/config/system.matlab_version', {
            key: 'system.matlab_version',
            value: val,
            description: 'MATLAB Runtime Version'
          })
       } else {
         throw e
       }
    })
    ElMessage.success('MATLAB version updated')
    fetchConfigs()
  } catch (e) {
    console.error(e)
    ElMessage.error('Failed to update MATLAB version')
  }
}

const handlePipelineRootChange = async (val: string) => {
  if (!val) return
  
  // 1. Validate
  try {
      const validateRes = await http.post('/system/pipelines/validate', { path: val })
      if (!validateRes.data.valid) {
            ElMessage.error(`Invalid Path: ${validateRes.data.error}`)
            fetchVersion() // Revert
            return
      }
  } catch(e) {
        ElMessage.error('Validation check failed')
        return
  }

  // 2. Confirm
  try {
      await ElMessageBox.confirm(
          'Switching MATLAB version may affect running tasks. Ensure compatibility before proceeding.',
          'Confirm Version Switch',
          { confirmButtonText: 'Switch', cancelButtonText: 'Cancel', type: 'warning' }
      )
  } catch {
      fetchVersion() // Revert
      return
  }

  // 3. Save
  try {
    // Check if config exists first (or upsert)
    // We'll use the generic save logic but specifically for this key
    await http.post('/system/config', {
      key: 'system.pipeline_root',
      value: val,
      description: 'MATLAB Pipeline Root Directory'
    }).catch(async (e) => {
       // If it fails, maybe it exists, try put
       if (e.response && e.response.status === 400) {
          await http.put('/system/config/system.pipeline_root', {
            key: 'system.pipeline_root',
            value: val,
            description: 'MATLAB Pipeline Root Directory'
          })
       } else {
         throw e
       }
    })
    ElMessage.success('MATLAB version updated')
    fetchVersion()
    fetchConfigs()
  } catch (e) {
    console.error(e)
    ElMessage.error('Failed to update MATLAB version')
  }
}

const fetchConfigs = async () => {
  loading.value = true
  try {
    const res = await http.get('/system/config')
    configs.value = res.data
    // Sync matlab version from config if exists
    const matlabConfig = configs.value.find(c => c.key === 'system.matlab_version')
    if (matlabConfig) {
      currentMatlabVersion.value = matlabConfig.value
    }
  } catch (e) {
    console.error(e)
    ElMessage.error('Failed to fetch configurations')
  } finally {
    loading.value = false
  }
}

const handleEdit = (row: AppConfig) => {
  isEdit.value = true
  form.value = { ...row }
  dialogVisible.value = true
}

const handleDelete = (row: AppConfig) => {
  ElMessageBox.confirm(
    'Are you sure to delete this config?',
    'Warning',
    {
      confirmButtonText: 'Yes',
      cancelButtonText: 'No',
      type: 'warning',
    }
  ).then(async () => {
    try {
      await http.delete(`/system/config/${row.key}`)
      ElMessage.success('Deleted successfully')
      fetchConfigs()
    } catch (e) {
      console.error(e)
      ElMessage.error('Failed to delete')
    }
  })
}

const saveConfig = async () => {
  submitting.value = true
  try {
    if (isEdit.value) {
      await http.put(`/system/config/${form.value.key}`, form.value)
    } else {
      await http.post('/system/config', form.value)
    }
    ElMessage.success('Saved successfully')
    dialogVisible.value = false
    fetchConfigs()
  } catch (e) {
    console.error(e)
    ElMessage.error('Failed to save')
  } finally {
    submitting.value = false
  }
}

watch(dialogVisible, (val) => {
  if (!val) {
    setTimeout(() => {
      isEdit.value = false
      form.value = { key: '', value: '', description: '' }
    }, 300)
  }
})

onMounted(() => {
  fetchPipelines()
  fetchConfigs()
  fetchVersion()
})
</script>

<style scoped>
.system-config-container {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  gap: 16px;
  align-items: center;
}
.version-tag {
  font-weight: bold;
}
.path-display-container {
  margin-top: 8px;
  color: #606266;
  font-size: 13px;
}
.path-display-box {
  margin-top: 5px;
  word-break: break-all;
  line-height: 1.5;
  font-family: monospace;
  background: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
  border: 1px solid #e4e7ed;
}
</style>
