document.addEventListener('DOMContentLoaded', function() {
    // تحميل المحادثات السابقة
    loadConversations();
    
    // إضافة حدث للمحادثة الجديدة
    document.getElementById('newChat').addEventListener('click', function() {
        if (confirm('هل تريد بدء محادثة جديدة؟ سيتم مسح تاريخ المحادثة الحالية.')) {
            // هنا سيتم إرسال طلب لإنشاء محادثة جديدة
            alert('سيتم تنفيذ هذه الميزة في الإصدارات القادمة');
        }
    });
    
    // تأثيرات ثلاثية الأبعاد للعناصر
    const elements = document.querySelectorAll('.sidebar, .chat-container');
    elements.forEach(el => {
        el.addEventListener('mousemove', function(e) {
            const xAxis = (window.innerWidth / 2 - e.pageX) / 25;
            const yAxis = (window.innerHeight / 2 - e.pageY) / 25;
            this.style.transform = `rotateY(${xAxis}deg) rotateX(${yAxis}deg)`;
        });
        
        el.addEventListener('mouseenter', function() {
            this.style.transition = 'all 0.1s ease';
        });
        
        el.addEventListener('mouseleave', function() {
            this.style.transition = 'all 0.5s ease';
            this.style.transform = 'rotateY(0deg) rotateX(0deg)';
        });
    });
});

function loadConversations() {
    // هنا سيتم جلب المحادثات من الخادم
    const conversationsList = document.querySelector('.conversations-list');
    
    // مثال بالمحادثات (سيتم استبدالها ببيانات حقيقية)
    const sampleConversations = [
        { id: 1, title: 'محادثة حول الذكاء الاصطناعي' },
        { id: 2, title: 'استفسار حول OTH IA' },
        { id: 3, title: 'تحليل صورة' }
    ];
    
    sampleConversations.forEach(conv => {
        const convItem = document.createElement('div');
        convItem.className = 'conversation-item';
        convItem.innerHTML = `
            <i class="fas fa-comment-alt"></i>
            <span>${conv.title}</span>
        `;
        conversationsList.appendChild(convItem);
    });
}
