<template>
  <div class="users-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>User Management</span>
          <el-button type="primary" @click="showCreateDialog = true">Create User</el-button>
        </div>
      </template>

      <el-table :data="users" style="width: 100%" v-loading="loading">
        <el-table-column prop="username" label="Username" />
        <el-table-column prop="role" label="Role">
          <template #default="scope">
            <el-tag :type="scope.row.role === 'admin' ? 'danger' : 'info'">{{ scope.row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="Created At">
          <template #default="scope">
            {{ new Date(scope.row.created_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showCreateDialog" title="Create New User">
      <el-form :model="createForm" label-width="120px">
        <el-form-item label="Username">
          <el-input v-model="createForm.username" />
        </el-form-item>
        <el-form-item label="Password">
          <el-input v-model="createForm.password" type="password" />
        </el-form-item>
        <el-form-item label="Role">
          <el-select v-model="createForm.role">
            <el-option label="User" value="user" />
            <el-option label="Admin" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showCreateDialog = false">Cancel</el-button>
          <el-button type="primary" @click="createUser">Confirm</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const users = ref([])
const loading = ref(false)
const showCreateDialog = ref(false)
const createForm = ref({
  username: '',
  password: '',
  role: 'user'
})

const fetchUsers = async () => {
  loading.value = true
  try {
    const res = await http.get('/users/')
    users.value = res.data
  } catch (error) {
    ElMessage.error('Failed to fetch users')
  } finally {
    loading.value = false
  }
}

const createUser = async () => {
  try {
    await http.post('/users/', createForm.value)
    ElMessage.success('User created successfully')
    showCreateDialog.value = false
    createForm.value = { username: '', password: '', role: 'user' }
    fetchUsers()
  } catch (error) {
    ElMessage.error('Failed to create user')
  }
}

onMounted(() => {
  fetchUsers()
})
</script>

<style scoped>
.users-container {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
