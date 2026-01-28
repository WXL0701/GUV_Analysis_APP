<template>
  <div class="task-queue-container">
    <div class="header">
      <h2>Task Queue Management</h2>
      <div class="actions">
        <el-button type="primary" @click="refreshAll">
          <el-icon><Refresh /></el-icon> Refresh
        </el-button>
      </div>
    </div>

    <!-- Stats Cards -->
    <div class="stats-row mb-4">
      <el-row :gutter="20">
        <el-col :span="8">
          <el-card shadow="hover" class="stats-card">
            <template #header>
              <div class="card-header">
                <span>Queue Statistics</span>
              </div>
            </template>
            <div class="stats-grid">
              <div class="stat-item">
                <div class="label">Total</div>
                <div class="value">{{ stats.total }}</div>
              </div>
              <div class="stat-item">
                <div class="label">Running</div>
                <div class="value primary">{{ stats.running }}</div>
              </div>
              <div class="stat-item">
                <div class="label">Queued</div>
                <div class="value warning">{{ stats.queued }}</div>
              </div>
              <div class="stat-item">
                <div class="label">Succeeded</div>
                <div class="value success">{{ stats.succeeded }}</div>
              </div>
              <div class="stat-item">
                <div class="label">Failed</div>
                <div class="value danger">{{ stats.failed }}</div>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="16">
          <el-card shadow="hover">
            <template #header>Recent Activity (7 Days)</template>
            <div ref="chartRef" style="height: 200px; width: 100%;"></div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- Task List -->
    <el-card class="queue-card">
      <template #header>
        <div class="card-header">
          <el-tabs v-model="activeTab" @tab-change="handleTabChange">
            <el-tab-pane label="Active Tasks" name="active">
              <template #label>
                <span>
                  <el-icon><VideoPlay /></el-icon> Active Tasks
                  <el-badge :value="stats.running + stats.queued" class="ml-2" type="primary" v-if="stats.running + stats.queued > 0" />
                </span>
              </template>
            </el-tab-pane>
            <el-tab-pane label="History" name="history">
              <template #label>
                 <span><el-icon><Clock /></el-icon> History</span>
              </template>
            </el-tab-pane>
            <el-tab-pane label="All Tasks" name="all">
              <template #label>
                 <span><el-icon><Files /></el-icon> All Tasks</span>
              </template>
            </el-tab-pane>
            <el-tab-pane label="Queue Logs" name="logs">
              <template #label>
                 <span><el-icon><List /></el-icon> Queue Logs</span>
              </template>
            </el-tab-pane>
          </el-tabs>
          <div class="header-right">
             <el-tag type="info">Auto-refresh: {{ autoRefresh ? 'On' : 'Off' }}</el-tag>
          </div>
        </div>
      </template>
      
      <div v-if="activeTab === 'logs'">
        <el-table :data="logs" style="width: 100%" v-loading="loadingLogs">
           <el-table-column prop="task_id" label="Task ID" width="200">
             <template #default="scope">
               <el-link type="primary" @click="$router.push(`/tasks/${scope.row.task_id}`)">{{ scope.row.task_id }}</el-link>
             </template>
           </el-table-column>
           <el-table-column label="Status" width="120">
              <template #default="scope">
                 <el-tag :type="getStatusType(scope.row.status)">{{ scope.row.status }}</el-tag>
              </template>
           </el-table-column>
           <el-table-column label="Created" width="180">
              <template #default="scope">{{ formatDate(scope.row.created_at) }}</template>
           </el-table-column>
           <el-table-column label="Started" width="180">
              <template #default="scope">{{ formatDate(scope.row.started_at) }}</template>
           </el-table-column>
           <el-table-column label="Completed" width="180">
              <template #default="scope">{{ formatDate(scope.row.completed_at) }}</template>
           </el-table-column>
           <el-table-column label="Duration" width="150">
              <template #default="scope">{{ calculateDuration(scope.row) }}</template>
           </el-table-column>
        </el-table>
      </div>
      
      <div v-else>
      <el-table :data="tasks" style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="ID" width="180" />
        <el-table-column prop="name" label="Name" min-width="150" />
        
        <el-table-column label="Status" width="120">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">{{ scope.row.status }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="Priority" width="150">
          <template #default="scope">
            <el-input-number 
              v-if="isActiveTask(scope.row)"
              v-model="scope.row.priority" 
              :min="0" 
              :max="100" 
              size="small"
              @change="(val: any) => updatePriority(scope.row, val)"
            />
            <span v-else>{{ scope.row.priority }}</span>
          </template>
        </el-table-column>

        <el-table-column label="Progress" width="200">
          <template #default="scope">
            <el-progress 
              :percentage="scope.row.progress || 0" 
              :status="scope.row.status === 'FAILED' ? 'exception' : (scope.row.status === 'SUCCEEDED' ? 'success' : '')"
            />
          </template>
        </el-table-column>
        
        <el-table-column label="Dependencies" min-width="150">
          <template #default="scope">
            <div class="dependencies-cell" @click="isActiveTask(scope.row) ? openDependencyDialog(scope.row) : null">
              <el-tag 
                v-for="dep in (scope.row.dependencies || [])" 
                :key="dep" 
                size="small" 
                class="mx-1"
                :closable="isActiveTask(scope.row)"
                @close="removeDependency(scope.row, dep)"
              >
                {{ dep }}
              </el-tag>
              <template v-if="isActiveTask(scope.row)">
                <el-button v-if="!scope.row.dependencies || scope.row.dependencies.length === 0" size="small" icon="Plus" circle @click.stop="openDependencyDialog(scope.row)" />
                <el-button v-else size="small" icon="Edit" circle class="ml-1" @click.stop="openDependencyDialog(scope.row)" />
              </template>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="Created At" width="180">
           <template #default="scope">
             {{ formatDate(scope.row.created_at) }}
           </template>
        </el-table-column>

        <el-table-column label="Actions" width="120" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="$router.push(`/tasks/${scope.row.id}`)">
              Details
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="fetchTasks"
          @current-change="fetchTasks"
        />
      </div>
      </div>
    </el-card>

    <!-- Dependency Edit Dialog -->
    <el-dialog v-model="dependencyDialogVisible" title="Edit Dependencies" width="500px">
      <el-form :model="currentTask">
        <el-form-item label="Task">
          <el-input v-if="currentTask" v-model="currentTask.name" disabled />
        </el-form-item>
        <el-form-item label="Dependencies">
          <el-select
            v-model="selectedDependencies"
            multiple
            placeholder="Select dependent tasks"
            style="width: 100%"
          >
            <el-option
              v-for="item in allTasks"
              :key="item.id"
              :label="item.name + ' (' + item.id + ')'"
              :value="item.id"
              :disabled="item.id === currentTask?.id" 
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dependencyDialogVisible = false">Cancel</el-button>
          <el-button type="primary" @click="saveDependencies">Confirm</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { Refresh, VideoPlay, Clock, Files, List } from '@element-plus/icons-vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'

const tasks = ref([])
const allTasks = ref<any[]>([]) // For dependency selection
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const autoRefresh = ref(true)
const activeTab = ref('active')
const chartRef = ref(null)
let chartInstance: any = null
let refreshTimer: any = null

const stats = ref({
  total: 0,
  running: 0,
  queued: 0,
  succeeded: 0,
  failed: 0,
  recent_activity: []
})

// Dependency Dialog
const dependencyDialogVisible = ref(false)
const currentTask = ref<any>(null)
const selectedDependencies = ref<string[]>([])

const getStatusType = (status: string) => {
  if (!status) return 'info'
  if (status === 'SUCCEEDED') return 'success'
  if (status === 'FAILED') return 'danger'
  if (status.startsWith('RUNNING')) return 'primary'
  if (status === 'QUEUED') return 'warning'
  return 'info'
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}

const isActiveTask = (task: any) => {
  return task.status === 'QUEUED' || (task.status && task.status.startsWith('RUNNING'))
}

const fetchStats = async () => {
  try {
    const res = await http.get('/tasks/stats')
    stats.value = res.data
    updateChart()
  } catch (e) {
    console.error(e)
  }
}

const fetchTasks = async () => {
  loading.value = true
  try {
    const res = await http.get('/tasks/', {
      params: {
        skip: (currentPage.value - 1) * pageSize.value,
        limit: pageSize.value,
        filter_type: activeTab.value
      }
    })
    tasks.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    console.error(e)
    ElMessage.error('Failed to fetch tasks')
  } finally {
    loading.value = false
  }
}

const refreshAll = () => {
  fetchTasks()
  fetchStats()
}

const logs = ref<any[]>([])
const loadingLogs = ref(false)

const fetchLogs = async () => {
  loadingLogs.value = true
  try {
    const res = await http.get('/tasks/queue/logs')
    logs.value = res.data
  } catch (e) {
    console.error(e)
  } finally {
    loadingLogs.value = false
  }
}

const calculateDuration = (row: any) => {
  if (!row.started_at || !row.completed_at) return '-'
  const start = new Date(row.started_at).getTime()
  const end = new Date(row.completed_at).getTime()
  const diff = (end - start) / 1000
  if (diff < 60) return diff.toFixed(1) + 's'
  return (diff / 60).toFixed(1) + 'm'
}

const handleTabChange = (tab: any) => {
  if (tab === 'logs') {
    fetchLogs()
  } else {
    currentPage.value = 1
    fetchTasks()
  }
}

// Fetch all tasks for dropdown (simplified)
const fetchAllTasks = async () => {
  try {
    const res = await http.get('/tasks/', {
      params: { skip: 0, limit: 1000 } 
    })
    allTasks.value = res.data.items
  } catch (e) {
    console.error(e)
  }
}

const updatePriority = async (task: any, newPriority: number | undefined) => {
  if (newPriority === undefined) return
  try {
    await http.put(`/tasks/${task.id}/queue-info`, {
      priority: newPriority
    })
    ElMessage.success(`Priority updated for ${task.name}`)
  } catch (e) {
    console.error(e)
    ElMessage.error('Failed to update priority')
    fetchTasks() 
  }
}

const openDependencyDialog = (task: any) => {
  currentTask.value = task
  selectedDependencies.value = [...(task.dependencies || [])]
  dependencyDialogVisible.value = true
  fetchAllTasks() // Refresh list
}

const saveDependencies = async () => {
  if (!currentTask.value) return
  try {
    await http.put(`/tasks/${currentTask.value.id}/queue-info`, {
      dependencies: selectedDependencies.value
    })
    ElMessage.success('Dependencies updated')
    dependencyDialogVisible.value = false
    fetchTasks()
  } catch (e) {
    console.error(e)
    ElMessage.error('Failed to update dependencies')
  }
}

const removeDependency = async (task: any, depId: string) => {
  const newDeps = (task.dependencies || []).filter((d: string) => d !== depId)
  try {
    await http.put(`/tasks/${task.id}/queue-info`, {
      dependencies: newDeps
    })
    ElMessage.success('Dependency removed')
    fetchTasks()
  } catch (e) {
    console.error(e)
    ElMessage.error('Failed to remove dependency')
  }
}

const initChart = () => {
  if (chartRef.value) {
    chartInstance = echarts.init(chartRef.value)
    updateChart()
  }
}

const updateChart = () => {
  if (!chartInstance || !stats.value.recent_activity) return
  
  const dates = stats.value.recent_activity.map((item: any) => item.date)
  const counts = stats.value.recent_activity.map((item: any) => item.count)
  
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisTick: { alignWithLabel: true }
    },
    yAxis: {
      type: 'value'
    },
    series: [
      {
        name: 'Tasks',
        type: 'bar',
        barWidth: '60%',
        data: counts,
        itemStyle: {
          color: '#409EFF'
        }
      }
    ]
  }
  
  chartInstance.setOption(option)
}

onMounted(() => {
  fetchTasks()
  fetchStats()
  nextTick(() => {
    initChart()
    window.addEventListener('resize', () => chartInstance?.resize())
  })
  
  refreshTimer = setInterval(() => {
    if (autoRefresh.value) {
      if (activeTab.value === 'logs') {
        // Silent refresh for logs
        http.get('/tasks/queue/logs').then(res => {
          logs.value = res.data
        })
      } else {
        // Silent refresh for tasks
        http.get('/tasks/', {
          params: {
            skip: (currentPage.value - 1) * pageSize.value,
            limit: pageSize.value,
            filter_type: activeTab.value
          }
        }).then(res => {
          tasks.value = res.data.items
          total.value = res.data.total
        })
      }
      // Also refresh stats
      fetchStats()
    }
  }, 5000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  window.removeEventListener('resize', () => chartInstance?.resize())
  chartInstance?.dispose()
})
</script>

<style scoped>
.task-queue-container {
  padding: 20px;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.stats-card {
  height: 100%;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 15px;
}
.stat-item {
  text-align: center;
  padding: 10px;
  background-color: var(--el-bg-color-page);
  border-radius: 8px;
}
.stat-item:first-child {
  grid-column: span 2;
}
.stat-item .label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 5px;
}
.stat-item .value {
  font-size: 20px;
  font-weight: bold;
}
.value.primary { color: var(--el-color-primary); }
.value.warning { color: var(--el-color-warning); }
.value.success { color: var(--el-color-success); }
.value.danger { color: var(--el-color-danger); }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.dependencies-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: center;
  cursor: pointer;
}
.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
.mb-4 {
  margin-bottom: 16px;
}
.ml-2 {
  margin-left: 8px;
}
</style>
