<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import App from "./App.vue";
import {
  authRequest,
  autoLoginKey,
  clearSavedLogin,
  loadSavedLogin,
  restoreSession,
  saveLogin,
  setAccessToken,
  type AuthUser,
  type SavedLogin,
} from "./auth";

type AuthMode = "login" | "register";
const mode = ref<AuthMode>("login");
const nickname = ref("");
const password = ref("");
const confirmPassword = ref("");
const autoLogin = ref(localStorage.getItem(autoLoginKey) === "true");
const agreementAccepted = ref(false);
const agreementOpen = ref(false);
const user = ref<AuthUser | null>(null);
const ready = ref(false);
const busy = ref(false);
const error = ref("");
const credentialSupported = Boolean(window.youxuebanCredentials);

onMounted(async () => {
  let savedLogin: SavedLogin | null = null;
  try {
    savedLogin = await loadSavedLogin();
    if (savedLogin) {
      nickname.value = savedLogin.nickname;
      password.value = savedLogin.password;
    }
    user.value = await restoreSession();
    if (!user.value && autoLogin.value && savedLogin) {
      await performAuth("login", savedLogin.nickname, savedLogin.password, true);
    }
    if (user.value) sessionStorage.setItem("youxueban-auth-user", JSON.stringify(user.value));
  } catch {
    error.value = "无法连接邮学伴服务端，请确认服务已启动或检查网络。";
  } finally {
    ready.value = true;
  }
  window.addEventListener("youxueban-auth-expired", handleExpired);
});

watch(autoLogin, (enabled) => {
  localStorage.setItem(autoLoginKey, String(enabled));
});

function handleExpired(): void {
  user.value = null;
  mode.value = "login";
  error.value = "登录会话已过期，请重新登录。";
}

async function performAuth(authMode: AuthMode, name: string, secret: string, rememberMe: boolean): Promise<boolean> {
  const path = authMode === "register" ? "/api/v1/auth/register" : "/api/v1/auth/login";
  const { response, payload } = await authRequest(path, {
    nickname: name,
    password: secret,
    rememberMe,
    ...(authMode === "register" ? { agreedToTerms: agreementAccepted.value } : {}),
  });
  if (!response.ok || !payload.user || !payload.accessToken) {
    error.value = payload.error || "登录失败，请检查输入。";
    return false;
  }
  setAccessToken(payload.accessToken);
  user.value = payload.user;
  sessionStorage.setItem("youxueban-auth-user", JSON.stringify(payload.user));
  return true;
}

async function submit(): Promise<void> {
  error.value = "";
  const name = nickname.value.trim();
  if (!name || name.length > 20) {
    error.value = "昵称长度应为 1 到 20 个字符。";
    return;
  }
  if (password.value.length < 6 || password.value.length > 128) {
    error.value = "密码长度应为 6 到 128 个字符。";
    return;
  }
  if (mode.value === "register" && password.value !== confirmPassword.value) {
    error.value = "两次输入的密码不一致。";
    return;
  }
  if (mode.value === "register" && !agreementAccepted.value) {
    error.value = "请先阅读并同意《邮学伴用户协议与隐私说明》。";
    return;
  }
  busy.value = true;
  try {
    const succeeded = await performAuth(mode.value, name, password.value, autoLogin.value);
    if (!succeeded) return;
    if (autoLogin.value && credentialSupported) await saveLogin({ nickname: name, password: password.value });
    else if (!autoLogin.value) await clearSavedLogin();
    nickname.value = "";
    password.value = "";
    confirmPassword.value = "";
  } catch (reason) {
    error.value = reason instanceof Error && reason.message.includes("安全保存")
      ? reason.message
      : "无法连接邮学伴服务端，请稍后重试。";
  } finally {
    busy.value = false;
  }
}

function switchMode(): void {
  mode.value = mode.value === "login" ? "register" : "login";
  confirmPassword.value = "";
  agreementAccepted.value = false;
  error.value = "";
}
</script>

<template>
  <div v-if="!ready || !user" class="auth-screen">
    <div class="auth-orb auth-orb-one" aria-hidden="true" />
    <div class="auth-orb auth-orb-two" aria-hidden="true" />
    <section class="auth-card" role="dialog" aria-modal="true" aria-labelledby="auth-title">
      <span class="brand-mark">邮</span>
      <span class="eyebrow">北邮人的学习与生活助手</span>
      <h1 id="auth-title">{{ mode === 'login' ? '登录邮学伴' : '创建邮学伴账号' }}</h1>
      <p>{{ mode === 'login' ? '登录后即可使用在线校园信息和学习助手。' : '账号只用于邮学伴服务，不等同于北邮统一认证账号。' }}</p>
      <form v-if="ready" @submit.prevent="submit">
        <label for="auth-account">昵称</label>
        <input id="auth-account" v-model="nickname" autocomplete="username" maxlength="20" placeholder="请输入昵称" />
        <label for="auth-password">密码</label>
        <input id="auth-password" v-model="password" type="password" :autocomplete="mode === 'register' ? 'new-password' : 'current-password'" placeholder="至少 6 位" />
        <label v-if="mode === 'register'" for="auth-confirm">确认密码</label>
        <input v-if="mode === 'register'" id="auth-confirm" v-model="confirmPassword" type="password" autocomplete="new-password" placeholder="再次输入密码" />

        <div class="auth-options">
          <label class="auth-check">
            <input v-model="autoLogin" type="checkbox" />
            <span>下次自动登录</span>
          </label>
          <small v-if="!credentialSupported">网页版不保存密码；桌面客户端可使用系统加密存储。</small>
        </div>

        <label v-if="mode === 'register'" class="auth-check agreement-check">
          <input v-model="agreementAccepted" type="checkbox" />
          <span>我已阅读并同意 <button type="button" @click.prevent="agreementOpen = true">《邮学伴用户协议与隐私说明》</button></span>
        </label>
        <p v-if="error" class="auth-error" role="alert">{{ error }}</p>
        <button class="primary-button full" type="submit" :disabled="busy || (mode === 'register' && !agreementAccepted)">{{ busy ? '请稍候…' : mode === 'login' ? '登录' : '注册并开始使用' }}</button>
      </form>
      <div v-else class="auth-loading">正在检查登录状态…</div>
      <button v-if="ready" class="auth-switch" type="button" @click="switchMode">
        {{ mode === 'login' ? '还没有账号？注册' : '已有账号？返回登录' }}
      </button>
      <small>个人任务、课程、对话和设置保存在本机；校园数据与 AI 请求需要连接服务端。</small>
    </section>

    <div v-if="agreementOpen" class="modal-backdrop auth-agreement-backdrop" @click.self="agreementOpen = false">
      <section class="modal agreement-modal" role="dialog" aria-modal="true" aria-labelledby="agreement-title">
        <header><div><span class="eyebrow">注册前必读</span><h2 id="agreement-title">邮学伴用户协议与隐私说明</h2></div><button class="icon-button" type="button" aria-label="关闭协议" @click="agreementOpen = false">×</button></header>
        <div class="agreement-content">
          <p>邮学伴用于整合学习任务、课程安排、校园只读信息与 AI 学习辅助。注册即表示你理解并接受以下数据处理方式：</p>
          <h3>1. 本机数据</h3><p>昵称、头像、任务、课程、提醒设置、已读状态和 AI 对话默认保存在当前设备，不会因退出账号而删除。重置个人信息时才会按你的确认清除。</p>
          <h3>2. 账号与登录</h3><p>服务端保存邮学伴账号、不可逆密码哈希和会话信息。开启“下次自动登录”时，桌面客户端使用操作系统加密能力保存本机登录信息；退出账号会清除该设备保存的登录信息。</p>
          <h3>3. 在线校园服务</h3><p>信息门户、第二课堂、教务与电费查询由服务端代理访问相应校园系统。服务端不会向客户端返回校园 Cookie、Token、统一认证密码或模型密钥，并会区分在线结果、缓存、空结果和失败状态。</p>
          <h3>4. AI 服务</h3><p>你发送的提问、选择上传的图片，以及在设置允许范围内的课程、任务或校园上下文，会转发至已配置的模型服务商以生成回答。请勿提交不必要的敏感信息。</p>
          <h3>5. 使用边界</h3><p>软件仅提供查询、整理与学习辅助，不代替学校官方系统，不绕过验证码、访问控制或校园系统规则。第二课堂只提供查询与订阅，不提供报名、签到或退选。</p>
          <h3>6. 你的选择</h3><p>你可以关闭个性化记忆、学习数据分析和桌面通知；可以退出账号而保留本机信息，也可以在危险区主动重置全部本机个人信息。</p>
        </div>
        <footer><button class="secondary-button" type="button" @click="agreementOpen = false">返回</button><button class="primary-button" type="button" @click="agreementAccepted = true; agreementOpen = false">同意并继续</button></footer>
      </section>
    </div>
  </div>
  <App v-else />
</template>
