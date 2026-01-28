<template>
  <div class="system-info">
    <h2>Server Status</h2>
    
    <el-alert
      v-if="alertMessage"
      :title="alertMessage"
      type="error"
      effect="dark"
      show-icon
      class="mb-4"
    />

    <el-row :gutter="20" v-if="stats">
      <!-- CPU -->
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>CPU Usage</span>
              <el-tag type="info">{{ stats.cpu.count }} Cores</el-tag>
            </div>
          </template>
          <div class="chart-container">
            <el-progress type="dashboard" :percentage="stats.cpu.percent" :color="colors" />
            <div class="stat-detail">
              <h3>{{ stats.cpu.percent }}%</h3>
              <p>Load</p>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- Memory -->
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>Memory Usage</span>
              <el-tag type="success">{{ formatBytes(stats.memory.total) }} Total</el-tag>
            </div>
          </template>
          <div class="chart-container">
            <el-progress type="dashboard" :percentage="stats.memory.percent" :color="colors" />
            <div class="stat-detail">
              <h3>{{ stats.memory.percent }}%</h3>
              <p>{{ formatBytes(stats.memory.used) }} Used</p>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- Disk -->
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>Disk Usage (/)</span>
              <el-tag type="warning">{{ formatBytes(stats.disk.total) }} Total</el-tag>
            </div>
          </template>
          <div class="chart-container">
            <el-progress type="dashboard" :percentage="stats.disk.percent" :color="colors" />
            <div class="stat-detail">
              <h3>{{ stats.disk.percent }}%</h3>
              <p>{{ formatBytes(stats.disk.free) }} Free</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px;" v-if="stats">
      <el-col :span="24">
        <el-card shadow="hover">
          <template #header>
            <span>History (Last 60 Minutes)</span>
          </template>
          <div ref="chartRef" style="height: 300px;"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px;" v-if="stats">
      <el-col :span="24">
        <el-card shadow="hover">
          <template #header>
            <span>System Information</span>
          </template>
          <el-descriptions :column="3" border>
            <el-descriptions-item label="OS System">{{ stats.platform.system }}</el-descriptions-item>
            <el-descriptions-item label="Node Name">{{ stats.platform.node }}</el-descriptions-item>
            <el-descriptions-item label="Release">{{ stats.platform.release }}</el-descriptions-item>
            <el-descriptions-item label="Version">{{ stats.platform.version }}</el-descriptions-item>
            <el-descriptions-item label="Machine">{{ stats.platform.machine }}</el-descriptions-item>
            <el-descriptions-item label="Processor">{{ stats.platform.processor }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <div v-else class="loading-container">
      <el-skeleton :rows="5" animated />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import http from '@/api/http'
import * as echarts from 'echarts'

const stats = ref<any>(null)
const chartRef = ref<HTMLElement | null>(null)
const alertMessage = ref('')
let chartInstance: echarts.ECharts | null = null
let interval: any = null

const colors = [
  { color: '#5cb87a', percentage: 60 },
  { color: '#e6a23c', percentage: 80 },
  { color: '#f56c6c', percentage: 100 },
]

const formatBytes = (bytes: number, decimals = 2) => {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

const fetchStats = async () => {
  try {
    const res = await http.get('/system/stats')
    stats.value = res.data
    
    // Check for alerts
    if (stats.value.cpu.percent > 90) {
      alertMessage.value = 'High CPU Usage Alert!'
    } else if (stats.value.memory.percent > 90) {
      alertMessage.value = 'High Memory Usage Alert!'
    } else {
      alertMessage.value = ''
    }
  } catch (e) {
    console.error(e)
  }
}

const fetchHistory = async () => {
  try {
    const res = await http.get('/system/history')
    const history = res.data
    updateChart(history)
  } catch (e) {
    console.error(e)
  }
}

const updateChart = (data: any[]) => {
  if (!chartRef.value) return
  
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const times = data.map(item => new Date(item.ts).toLocaleTimeString())
  const cpu = data.map(item => item.cpu_percent)
  const memory = data.map(item => item.memory_percent)
  const disk = data.map(item => item.disk_percent)

  const option = {
    tooltip: {
      trigger: 'axis'
    },
    legend: {
      data: ['CPU', 'Memory', 'Disk'],
      right: 10,
      top: 0
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: times
    },
    yAxis: {
      type: 'value',
      max: 100
    },
    series: [
      {
        name: 'CPU',
        type: 'line',
        data: cpu,
        smooth: true,
        showSymbol: false,
      },
      {
        name: 'Memory',
        type: 'line',
        data: memory,
        smooth: true,
        showSymbol: false,
      },
      {
        name: 'Disk',
        type: 'line',
        data: disk,
        smooth: true,
        showSymbol: false,
      }
    ]
  }

  chartInstance.setOption(option)
}

onMounted(() => {
  fetchStats()
  fetchHistory()
  interval = setInterval(() => {
    fetchStats()
    fetchHistory()
  }, 3000) // Poll every 3 seconds for real-time feel, though history updates every minute
  
  window.addEventListener('resize', () => {
    chartInstance?.resize()
  })
})

onUnmounted(() => {
  if (interval) clearInterval(interval)
  chartInstance?.dispose()
  window.removeEventListener('resize', () => {
    chartInstance?.resize()
  })
})
</script>

<style scoped>
.system-info {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.chart-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px 0;
}
.stat-detail {
  margin-top: 10px;
  text-align: center;
}
.stat-detail h3 {
  margin: 0;
  font-size: 24px;
  color: #303133;
}
.stat-detail p {
  margin: 5px 0 0;
  color: #909399;
}
.mb-4 {
  margin-bottom: 20px;
}
</style>
