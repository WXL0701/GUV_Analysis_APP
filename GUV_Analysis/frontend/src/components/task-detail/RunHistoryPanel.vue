<template>
  <el-card class="panel-card">
    <template #header>
      <div class="panel-header">
        <span>Run History</span>
        <el-button
          type="danger"
          size="small"
          :disabled="selectedCount === 0"
          @click="$emit('delete-selected')"
        >
          Delete Selected
        </el-button>
      </div>
    </template>
    <el-table
      :data="history"
      @selection-change="(rows: any[]) => $emit('selection-change', rows)"
      style="width: 100%"
      stripe
      highlight-current-row
    >
      <el-table-column type="selection" width="55" />
      <el-table-column prop="created_at" label="Date" width="180" sortable>
        <template #default="scope">
          {{ new Date(scope.row.created_at).toLocaleString() }}
        </template>
      </el-table-column>
      <el-table-column
        prop="run_mode"
        label="Mode"
        width="100"
        :filters="[
          { text: 'Debug', value: 'debug' },
          { text: 'Final', value: 'final' },
          { text: 'Video', value: 'video' },
        ]"
        :filter-method="(value: any, row: any) => row.run_mode === value"
      >
        <template #default="scope">
          <el-tag :type="runModeTagType(scope.row.run_mode)">{{ scope.row.run_mode }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="params_snapshot" label="Params" min-width="200">
        <template #default="scope">
          <div v-if="scope.row.params_snapshot" class="tag-list">
            <el-tag size="small" type="info" v-if="scope.row.params_snapshot.PixelSize_um">
              Px: {{ scope.row.params_snapshot.PixelSize_um }}
            </el-tag>
            <el-tag size="small" type="info" v-if="scope.row.params_snapshot.FrameInterval_s">
              Int: {{ scope.row.params_snapshot.FrameInterval_s }}s
            </el-tag>
            <el-tag size="small" type="warning" v-if="scope.row.params_snapshot.Debug?.Enable">
              Debug
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        prop="status"
        label="Status"
        width="120"
        :filters="[
          { text: 'RUNNING', value: 'RUNNING' },
          { text: 'SUCCEEDED', value: 'SUCCEEDED' },
          { text: 'FAILED', value: 'FAILED' },
        ]"
        :filter-method="(value: any, row: any) => row.status === value"
      >
        <template #default="scope">
          <el-tag :type="statusTagType(scope.row.status)">{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="id" label="Run ID" width="280">
        <template #default="scope">
          <el-link type="primary" @click="$emit('view-run', scope.row)">{{ scope.row.id }}</el-link>
        </template>
      </el-table-column>
      <el-table-column label="Actions">
        <template #default="scope">
          <el-button size="small" type="primary" @click="$emit('view-run', scope.row)">View</el-button>
          <el-button size="small" type="danger" @click="$emit('delete-run', scope.row.id)">Delete</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
defineProps<{
  history: any[]
  selectedCount: number
}>()

defineEmits<{
  (e: 'selection-change', rows: any[]): void
  (e: 'view-run', run: any): void
  (e: 'delete-run', runId: string): void
  (e: 'delete-selected'): void
}>()

const runModeTagType = (mode: string) => {
  if (mode === 'debug') return 'warning'
  if (mode === 'video') return 'primary'
  if (mode === 'final') return 'success'
  return 'info'
}

const statusTagType = (status: string) => {
  if (status === 'RUNNING' || status === 'QUEUED') return 'primary'
  if (status === 'FAILED') return 'danger'
  if (status === 'CANCELED') return 'warning'
  return 'success'
}
</script>

<style scoped>
.panel-card {
  margin-bottom: 20px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.tag-list {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}
</style>
