document.addEventListener('DOMContentLoaded', function() {
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');
    const chatMessages = document.getElementById('chatMessages');
    const typingIndicator = document.getElementById('typingIndicator');
    const fileInput = document.getElementById('fileInput');
    
    // إرسال الرسالة عند الضغط على Enter
    messageInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && messageInput.value.trim() !== '') {
            sendMessage();
        }
    });
    
    // إرسال الرسالة عند النقر على الزر
    sendButton.addEventListener('click', function() {
        if (messageInput.value.trim() !== '') {
            sendMessage();
        }
    });
    
    // معالجة تحميل الصور
    fileInput.addEventListener('change', function(e) {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            if (file.type.startsWith('image/')) {
                uploadImage(file);
            } else {
                alert('الرجاء اختيار ملف صورة فقط');
            }
        }
    });
    
    function sendMessage() {
        const message = messageInput.value.trim();
        addMessageToChat('user', message);
        messageInput.value = '';
        
        // إظهار مؤشر الكتابة
        typingIndicator.classList.add('active');
        
        // إرسال الرسالة إلى الخادم
        fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message: message })
        })
        .then(response => response.json())
        .then(data => {
            typingIndicator.classList.remove('active');
            
            if (data.error) {
                addMessageToChat('bot', 'حدث خطأ أثناء معالجة طلبك');
            } else {
                addMessageToChat('bot', data.formatted_response, true);
            }
        })
        .catch(error => {
            typingIndicator.classList.remove('active');
            addMessageToChat('bot', 'حدث خطأ في الاتصال بالخادم');
            console.error('Error:', error);
        });
    }
    
    function uploadImage(file) {
        const reader = new FileReader();
        
        reader.onload = function(e) {
            // عرض الصورة للمستخدم
            addImageToChat('user', e.target.result);
            
            // هنا سيتم إرسال الصورة إلى الخادم للتحليل
            typingIndicator.classList.add('active');
            
            // في هذا المثال سنستخدم رسالة وهمية
            setTimeout(() => {
                typingIndicator.classList.remove('active');
                addMessageToChat('bot', 'هذه ميزة تجريبية. في الإصدار الكامل، سيتم تحليل الصورة وإرسال النتائج.');
            }, 2000);
        };
        
        reader.readAsDataURL(file);
    }
    
    function addMessageToChat(sender, message, isFormatted = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        if (isFormatted) {
            contentDiv.innerHTML = message;
        } else {
            contentDiv.textContent = message;
        }
        
        const metaDiv = document.createElement('div');
        metaDiv.className = 'message-meta';
        metaDiv.textContent = sender === 'user' ? 'أنت' : 'OTH IA';
        
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(metaDiv);
        chatMessages.appendChild(messageDiv);
        
        // التمرير إلى الأسفل
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    function addImageToChat(sender, imageData) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const img = document.createElement('img');
        img.src = imageData;
        img.style.maxWidth = '100%';
        img.style.borderRadius = '8px';
        
        contentDiv.appendChild(img);
        messageDiv.appendChild(contentDiv);
        
        const metaDiv = document.createElement('div');
        metaDiv.className = 'message-meta';
        metaDiv.textContent = sender === 'user' ? 'أنت' : 'OTH IA';
        messageDiv.appendChild(metaDiv);
        
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    // وظيفة نسخ الأكواد
    window.copyCode = function(button) {
        const codeBlock = button.parentElement;
        const code = codeBlock.querySelector('code').textContent;
        
        navigator.clipboard.writeText(code).then(() => {
            button.textContent = 'تم النسخ!';
            setTimeout(() => {
                button.textContent = 'نسخ';
            }, 2000);
        });
    };
    
    // رسالة ترحيبية أولية
    setTimeout(() => {
        addMessageToChat('bot', 'مرحباً! أنا OTH IA، كيف يمكنني مساعدتك اليوم؟');
    }, 1000);
});
