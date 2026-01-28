<template>
  <div class="login-container">
    <el-card class="login-card">
      <template #header>
        <div class="card-header">
          <span>{{ isRegister ? 'Create Account' : 'GUV Analysis Platform Login' }}</span>
        </div>
      </template>
      <el-form :model="form" @submit.prevent="handleSubmit">
        <el-form-item label="Username" prop="username">
          <el-input v-model="form.username" placeholder="Username"></el-input>
        </el-form-item>
        <el-form-item label="Password" prop="password">
          <el-input v-model="form.password" type="password" placeholder="Password"></el-input>
        </el-form-item>
        <el-form-item v-if="isRegister" label="Confirm Password" prop="confirmPassword">
          <el-input v-model="form.confirmPassword" type="password" placeholder="Confirm Password"></el-input>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" native-type="submit" :loading="loading" class="w-100">
            {{ isRegister ? 'Register' : 'Login' }}
          </el-button>
        </el-form-item>
        <div class="text-center">
          <el-button link type="primary" @click="toggleMode">
            {{ isRegister ? 'Already have an account? Login' : 'Register New Account' }}
          </el-button>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const router = useRouter()
const isRegister = ref(false)
const form = ref({
  username: '',
  password: '',
  confirmPassword: ''
})
const loading = ref(false)

const toggleMode = () => {
  isRegister.value = !isRegister.value
  form.value = {
    username: '',
    password: '',
    confirmPassword: ''
  }
}

const handleSubmit = async () => {
  if (isRegister.value) {
    await handleRegister()
  } else {
    await handleLogin()
  }
}

const handleLogin = async () => {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning('Please enter username and password')
    return
  }
  loading.value = true
  try {
    const formData = new FormData()
    formData.append('username', form.value.username)
    formData.append('password', form.value.password)
    
    const res = await http.post('/auth/login', formData)
    const token = res.data.access_token
    sessionStorage.setItem('token', token)
    sessionStorage.setItem('username', form.value.username)
    
    // Clear localStorage to avoid confusion from legacy sessions
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    
    ElMessage.success('Login successful')
    router.push('/')
  } catch (error) {
    ElMessage.error('Login failed: Invalid credentials')
  } finally {
    loading.value = false
  }
}

const handleRegister = async () => {
  // Validation
  if (!form.value.username || !form.value.password || !form.value.confirmPassword) {
    ElMessage.warning('Please fill in all fields')
    return
  }
  if (form.value.password !== form.value.confirmPassword) {
    ElMessage.error('Passwords do not match')
    return
  }
  
  // Password complexity check
  const password = form.value.password
  if (password.length < 8) {
    ElMessage.error('Password must be at least 8 characters long')
    return
  }
  if (!/^[a-zA-Z0-9]+$/.test(password)) {
    ElMessage.error('Password can only contain letters and numbers')
    return
  }

  loading.value = true
  try {
    const res = await http.post('/auth/register', {
      username: form.value.username,
      password: form.value.password
    })
    
    const token = res.data.access_token
    sessionStorage.setItem('token', token)
    sessionStorage.setItem('username', form.value.username)
    
    // Clear localStorage
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    
    ElMessage.success('Registration successful')
    router.push('/')
  } catch (error: any) {
    const msg = error.response?.data?.detail || 'Registration failed'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background-color: #f5f7fa;
}
.login-card {
  width: 400px;
}
.card-header {
  text-align: center;
  font-weight: bold;
  font-size: 1.2rem;
}
.w-100 {
  width: 100%;
}
.text-center {
  text-align: center;
  margin-top: 10px;
}
</style>
