<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
      <h2>Task History</h2>
      <div style="display: flex; gap: 10px;">
          <el-input v-model="searchQuery" placeholder="Search by ID or Name" style="width: 250px;" @keyup.enter="handleSearch" clearable @clear="handleSearch">
              <template #append>
                  <el-button @click="handleSearch"><el-icon><Search /></el-icon></el-button>
              </template>
          </el-input>
          <el-button @click="fetchTasks">Refresh</el-button>
      </div>
    </div>
    
    <el-table :data="tasks" style="width: 100%" v-loading="loading" stripe border>
      <el-table-column prop="id" label="ID" width="180">
        <template #default="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column prop="name" label="Name" min-width="180" />
      <el-table-column prop="owner_name" label="Creator" width="150" />
      <el-table-column prop="created_at" label="Created At" width="180">
          <template #default="scope">
              {{ new Date(scope.row.created_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) }}
          </template>
      </el-table-column>
      <el-table-column prop="status" label="Status" width="150">
        <template #default="scope">
          <el-tag :type="getStatusType(scope.row.status)">
            {{ scope.row.status }}<span v-if="scope.row.status === 'QUEUED' && scope.row.queue_position"> (#{{ scope.row.queue_position }})</span>
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="progress" label="Progress" width="160">
        <template #default="scope">
          <el-progress
            v-if="typeof scope.row.progress === 'number' && scope.row.progress > 0 && scope.row.progress < 100"
            :percentage="scope.row.progress"
            :show-text="false"
          />
          <span v-else-if="scope.row.progress === 100">100%</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="Actions" width="250" fixed="right">
        <template #default="scope">
          <el-button 
            type="primary" 
            size="small"
            @click="$router.push(`/tasks/${scope.row.id}`)"
          >
            Configure & Run
          </el-button>
          <el-button 
            type="danger" 
            size="small"
            @click="handleDelete(scope.row)"
          >
            Delete
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    
    <div style="margin-top: 20px; display: flex; justify-content: flex-end;">
        <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            :total="total"
            @size-change="fetchTasks"
            @current-change="fetchTasks"
        />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import http from '@/api/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'

interface Task {
  id: string;
  name: string;
  status: string;
  progress?: number;
  created_at: string;
  owner_name?: string;
}

const tasks = ref<Task[]>([])
const loading = ref(false)
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0) // Note: Backend currently doesn't return total count for search, we might need to adjust or live with approximate pagination if we don't update backend to return total.
// Actually, standard pagination requires total. 
// For now, let's assume infinite scroll or just showing what we have.
// Wait, to do this properly, the backend should return {items: [], total: count}.
// The current backend returns List[TaskOut]. 
// So 'total' won't be accurate unless I change the backend return type.
// Given the constraints, I will fetch a slightly larger limit or just accept that "total" is unknown and use "next" button style?
// OR, I can update the backend to return a Page.

// Let's check backend read_tasks again. It returns List[TaskOut].
// To be clean, I should wrap it. But that might break other things.
// For now, I'll keep the backend simple and just fetch 'limit' items. 
// If I get 'limit' items, there might be more. 
// However, to satisfy "Pagination", knowing the total is best.
// I'll stick to a simple table for now but with the controls.
// Actually, I'll update the fetchTasks to just handle the current page logic assuming the backend behaves.
// Since I cannot easily change the return type without breaking potential other consumers (though I am the only one?), 
// I will just use the returned array length for now and maybe fetch all if the dataset isn't huge? 
// The user asked for "Pagination".
// I'll modify the backend to return total count in a header or change the response model?
// Changing response model is cleaner but requires updating frontend types.
// Let's just implement the UI and pass skip/limit.
// I'll set 'total' to a high number if I get a full page, or just hide the total.
// Better: I'll make a quick update to backend to return total via headers? No, that's messy.
// I'll just leave 'total' as 0 for now and let the user page through until empty?
// No, I'll implement a separate count endpoint or just fetch all for now (client side pagination) if the list is small?
// "tasks = db.query(Task)...limit(limit)"
// Let's just assume we can fetch up to 1000 and client-side paginate for this iteration to ensure stability.
// It's a "Task Management System", not a "Big Data System" yet.
// Re-reading: "实现分页和搜索功能".
// Okay, I'll do client side pagination for now to be safe and fast.
// I'll fetch with a large limit (e.g. 1000) and filter/paginate in frontend.

const fetchTasks = async () => {
  loading.value = true
  try {
    const { data } = await http.get('/tasks/', {
        params: {
            skip: (currentPage.value - 1) * pageSize.value, 
            limit: pageSize.value,
            q: searchQuery.value
        }
    })
    
    // Check if backend returns new paginated format
    if (data.items && typeof data.total === 'number') {
        tasks.value = data.items
        total.value = data.total
    } else {
        // Fallback for array response (should not happen if backend is updated)
        tasks.value = data
        total.value = data.length // approximate
    }
    
  } catch (e) {
    console.error(e)
    ElMessage.error('Failed to load tasks')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
    currentPage.value = 1
    fetchTasks()
}

const handleDelete = async (task: Task) => {
    try {
        await ElMessageBox.confirm(
            `Are you sure you want to delete task "${task.name}" (${task.id})? This will delete all associated data and files.`,
            'Warning',
            {
                confirmButtonText: 'Delete',
                cancelButtonText: 'Cancel',
                type: 'warning',
            }
        )
        
        loading.value = true
        await http.delete(`/tasks/${task.id}`)
        ElMessage.success('Task deleted successfully')
        fetchTasks()
        
    } catch (e: any) {
        if (e !== 'cancel') {
            ElMessage.error('Failed to delete task: ' + (e.response?.data?.detail || e.message))
        }
    } finally {
        loading.value = false
    }
}

onMounted(() => {
  fetchTasks()
})

const getStatusType = (status: string) => {
  if (status === 'SUCCEEDED' || status === 'UPLOADED') return 'success'
  if (status === 'FAILED') return 'danger'
  if (status.includes('RUNNING') || status === 'QUEUED' || status.includes('STAGE')) return 'warning'
  return 'info'
}
</script>
