<template>
  <div class="dashboard-container">
    <h2>Dashboard</h2>
    
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <template #header>
            <div class="card-header">
              <span>Total Tasks</span>
            </div>
          </template>
          <div class="stat-value">{{ stats.total }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <template #header>
            <div class="card-header">
              <span>Running</span>
            </div>
          </template>
          <div class="stat-value text-primary">{{ stats.running }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <template #header>
            <div class="card-header">
              <span>Succeeded</span>
            </div>
          </template>
          <div class="stat-value text-success">{{ stats.succeeded }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <template #header>
            <div class="card-header">
              <span>Failed</span>
            </div>
          </template>
          <div class="stat-value text-danger">{{ stats.failed }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <span>Recent Activity (Last 7 Days)</span>
          </template>
          <div ref="barChartRef" style="height: 300px;"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <span>Task Status Distribution</span>
          </template>
          <div ref="pieChartRef" style="height: 300px;"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import http from '@/api/http'
import * as echarts from 'echarts'

const stats = ref({
  total: 0,
  succeeded: 0,
  failed: 0,
  running: 0,
  recent_activity: [] as any[]
})

const barChartRef = ref<HTMLElement | null>(null)
const pieChartRef = ref<HTMLElement | null>(null)
let barChart: echarts.ECharts | null = null
let pieChart: echarts.ECharts | null = null

const fetchStats = async () => {
  try {
    const res = await http.get('/tasks/stats')
    stats.value = res.data
    updateCharts()
  } catch (e) {
    console.error(e)
  }
}

const updateCharts = () => {
  if (!barChartRef.value || !pieChartRef.value) return

  if (!barChart) barChart = echarts.init(barChartRef.value)
  if (!pieChart) pieChart = echarts.init(pieChartRef.value)

  // Bar Chart
  const dates = stats.value.recent_activity.map(item => item.date)
  const counts = stats.value.recent_activity.map(item => item.count)
  
  barChart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value' },
    series: [{ data: counts, type: 'bar', color: '#409EFF' }]
  })

  // Pie Chart
  pieChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: '5%', left: 'center' },
    series: [
      {
        name: 'Status',
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: { show: false, position: 'center' },
        emphasis: {
          label: { show: true, fontSize: 20, fontWeight: 'bold' }
        },
        data: [
          { value: stats.value.succeeded, name: 'Succeeded', itemStyle: { color: '#67C23A' } },
          { value: stats.value.failed, name: 'Failed', itemStyle: { color: '#F56C6C' } },
          { value: stats.value.running, name: 'Running', itemStyle: { color: '#409EFF' } },
          { value: stats.value.total - stats.value.succeeded - stats.value.failed - stats.value.running, name: 'Other', itemStyle: { color: '#909399' } }
        ]
      }
    ]
  })
}

onMounted(() => {
  fetchStats()
  window.addEventListener('resize', resizeCharts)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeCharts)
  barChart?.dispose()
  pieChart?.dispose()
})

const resizeCharts = () => {
  barChart?.resize()
  pieChart?.resize()
}
</script>

<style scoped>
.stat-card {
  text-align: center;
}
.stat-value {
  font-size: 24px;
  font-weight: bold;
}
.text-primary { color: #409EFF; }
.text-success { color: #67C23A; }
.text-danger { color: #F56C6C; }
</style>
