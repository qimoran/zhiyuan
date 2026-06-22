/**
 * AI 助手聊天组件
 *
 * 功能：
 * - 浮动聊天窗口
 * - Markdown 渲染
 * - 对话历史记忆
 * - 页面链接跳转
 */

class ChatAssistant {
  constructor() {
    this.chatHistory = [];
    this.isOpen = false;
    this.isLoading = false;
    this.init();
  }

  init() {
    this.createChatUI();
    this.bindEvents();
    this.loadHistory();
  }

  createChatUI() {
    const chatHTML = `
      <div class="chat-assistant" data-chat-assistant>
        <button class="chat-toggle" data-chat-toggle aria-label="打开 AI 助手">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          </svg>
          <span class="chat-badge" data-chat-badge style="display: none;">1</span>
        </button>

        <div class="chat-window" data-chat-window style="display: none;">
          <div class="chat-header">
            <div class="chat-title">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M8 14s1.5 2 4 2 4-2 4-2"></path>
                <line x1="9" y1="9" x2="9.01" y2="9"></line>
                <line x1="15" y1="9" x2="15.01" y2="9"></line>
              </svg>
              <span>AI 助手</span>
            </div>
            <button class="chat-close" data-chat-close aria-label="关闭">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>

          <div class="chat-messages" data-chat-messages>
            <div class="chat-message chat-message-assistant">
              <div class="chat-message-content">
                <p>你好！我是考研择校推荐系统的 AI 助手。</p>
                <p>您可以问我关于网站功能、使用方法、考研择校的问题，我会尽力帮您解答！</p>
              </div>
            </div>
          </div>

          <div class="chat-input-wrapper">
            <textarea
              class="chat-input"
              data-chat-input
              placeholder="输入您的问题..."
              rows="1"
              aria-label="输入消息"
            ></textarea>
            <button class="chat-send" data-chat-send aria-label="发送">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', chatHTML);
  }

  bindEvents() {
    const toggleBtn = document.querySelector('[data-chat-toggle]');
    const closeBtn = document.querySelector('[data-chat-close]');
    const sendBtn = document.querySelector('[data-chat-send]');
    const input = document.querySelector('[data-chat-input]');

    toggleBtn?.addEventListener('click', () => this.toggleChat());
    closeBtn?.addEventListener('click', () => this.closeChat());
    sendBtn?.addEventListener('click', () => this.sendMessage());

    input?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });

    // 自动调整 textarea 高度
    input?.addEventListener('input', (e) => {
      e.target.style.height = 'auto';
      e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
    });
  }

  toggleChat() {
    if (this.isOpen) {
      this.closeChat();
    } else {
      this.openChat();
    }
  }

  openChat() {
    const window = document.querySelector('[data-chat-window]');
    const badge = document.querySelector('[data-chat-badge]');

    if (window) {
      window.style.display = 'flex';
      this.isOpen = true;

      // 隐藏未读标记
      if (badge) {
        badge.style.display = 'none';
      }

      // 聚焦输入框
      setTimeout(() => {
        document.querySelector('[data-chat-input]')?.focus();
      }, 100);

      // 滚动到底部
      this.scrollToBottom();
    }
  }

  closeChat() {
    const window = document.querySelector('[data-chat-window]');
    if (window) {
      window.style.display = 'none';
      this.isOpen = false;
    }
  }

  async sendMessage() {
    const input = document.querySelector('[data-chat-input]');
    const message = input?.value.trim();

    if (!message || this.isLoading) {
      return;
    }

    // 清空输入框
    if (input) {
      input.value = '';
      input.style.height = 'auto';
    }

    // 添加用户消息
    this.addMessage('user', message);
    this.chatHistory.push({ role: 'user', content: message });

    // 显示加载状态
    this.isLoading = true;
    this.showTypingIndicator();

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: message,
          history: this.chatHistory.slice(-10), // 只发送最近 10 轮对话
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();

      if (data.code !== 0) {
        throw new Error(data.message || '请求失败');
      }

      const assistantMessage = data.data?.message || '抱歉，我暂时无法回答这个问题。';

      // 移除加载指示器
      this.removeTypingIndicator();

      // 添加助手回复
      this.addMessage('assistant', assistantMessage);
      this.chatHistory.push({ role: 'assistant', content: assistantMessage });

      // 保存对话历史
      this.saveHistory();

    } catch (error) {
      console.error('AI 助手请求失败：', error);
      this.removeTypingIndicator();

      const fallbackMessage = '抱歉，我暂时无法回答。您可以：\n\n- 前往 [开始推荐](/recommend) 获取择校推荐\n- 查看 [学校列表](/universities) 和 [专业列表](/majors)\n- 查看 [数据图表](/charts) 了解历年分数线趋势';

      this.addMessage('assistant', fallbackMessage);
    } finally {
      this.isLoading = false;
    }
  }

  addMessage(role, content) {
    const messagesContainer = document.querySelector('[data-chat-messages]');
    if (!messagesContainer) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message chat-message-${role}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'chat-message-content';

    if (role === 'assistant') {
      // 渲染 Markdown（简单版本）
      contentDiv.innerHTML = this.renderMarkdown(content);
    } else {
      contentDiv.textContent = content;
    }

    messageDiv.appendChild(contentDiv);
    messagesContainer.appendChild(messageDiv);

    this.scrollToBottom();
  }

  renderMarkdown(text) {
    // 简单的 Markdown 渲染
    let html = text
      // 转义 HTML
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      // 链接 [text](url)
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="chat-link">$1</a>')
      // 粗体 **text**
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      // 代码 `code`
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      // 换行
      .replace(/\n/g, '<br>');

    return html;
  }

  showTypingIndicator() {
    const messagesContainer = document.querySelector('[data-chat-messages]');
    if (!messagesContainer) return;

    const typingDiv = document.createElement('div');
    typingDiv.className = 'chat-message chat-message-assistant chat-typing';
    typingDiv.setAttribute('data-typing-indicator', '');
    typingDiv.innerHTML = `
      <div class="chat-message-content">
        <div class="chat-typing-dots">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </div>
    `;

    messagesContainer.appendChild(typingDiv);
    this.scrollToBottom();
  }

  removeTypingIndicator() {
    const indicator = document.querySelector('[data-typing-indicator]');
    indicator?.remove();
  }

  scrollToBottom() {
    const messagesContainer = document.querySelector('[data-chat-messages]');
    if (messagesContainer) {
      setTimeout(() => {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      }, 100);
    }
  }

  saveHistory() {
    try {
      localStorage.setItem('chatHistory', JSON.stringify(this.chatHistory.slice(-20)));
    } catch (error) {
      console.warn('保存对话历史失败：', error);
    }
  }

  loadHistory() {
    try {
      const saved = localStorage.getItem('chatHistory');
      if (saved) {
        this.chatHistory = JSON.parse(saved);

        // 恢复历史消息（跳过欢迎消息）
        this.chatHistory.forEach(msg => {
          if (msg.role && msg.content) {
            this.addMessage(msg.role, msg.content);
          }
        });
      }
    } catch (error) {
      console.warn('加载对话历史失败：', error);
    }
  }
}

// 页面加载完成后初始化
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    window.chatAssistant = new ChatAssistant();
  });
} else {
  window.chatAssistant = new ChatAssistant();
}
