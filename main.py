import feedparser
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import time
import os

# ==========================================
# 1. إعدادات المفاتيح والاتصال بالخدمات
# ==========================================

# إعداد مفتاح الذكاء الاصطناعي (Gemini) لإعادة الصياغة والترجمة
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# إعداد معلومات مدونة بلوجر
BLOG_ID = os.environ.get("BLOG_ID")

import json  # تأكد من وجود هذا الاستدعاء في أعلى الملف مع المكتبات

# ========================================================
# جزء المصادقة المعالج والمقاوم للأخطاء لـ token.json
# ========================================================
try:
    with open('token.json', 'r', encoding='utf-8') as f:
        token_data = json.load(f)
    
    # إذا كانت البيانات داخل قائمة مغلّفة [ ]، نأخذ القاموس الداخلي الأول { }
    if isinstance(token_data, list):
        if len(token_data) > 0:
            token_data = token_data[0]
        else:
            raise ValueError("ملف token.json يحتوي على قائمة فارغة!")

    # بناء الاعتماديات باستخدام البيانات المعالجة بشكل صحيح
    creds = Credentials.from_authorized_user_info(token_data)
    blogger_service = build('blogger', 'v3', credentials=creds)
    print("تمت عملية المصادقة وقراءة صلاحيات بلوجر بنجاح! 🔓")

except Exception as e:
    print(f"خطأ حرج أثناء معالجة ملف token.json: {e}")
    raise e

# ==========================================
# 2. إعداد مصادر الأخبار والتصنيفات
# ==========================================

# قائمة بالمصادر: نضع رابط الـ RSS والتصنيف (Label) الذي سيتم النشر تحته
FEEDS = [
    {"url": "https://techcrunch.com/rss", "label": "تكنولوجيا عالمية"},
    {"url": "https://aitnews.com/rss", "label": "هواتف ذكية"},
]

# ملف لحفظ الروابط التي تم نشرها لتجنب التكرار
HISTORY_FILE = "posted_urls.txt"

def get_posted_urls():
    """دالة لقراءة الروابط التي تم نشرها سابقاً من الملف النصي."""
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return f.read().splitlines()

def save_posted_url(url):
    """دالة لحفظ الرابط الجديد في الملف النصي بعد نشره."""
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")

# ==========================================
# 3. دالة المعالجة بالذكاء الاصطناعي
# ==========================================

def process_content_with_ai(title, content):
    """
    هذه الدالة ترسل النص للذكاء الاصطناعي لترجمته (إن لزم الأمر)،
    وتلخيصه، وإعادة صياغته بأسلوب تقني.
    """
    prompt = f"""
    أنت مدون تقني محترف. قم بالمهمة التالية على النص المرفق:
    1. إذا كان النص باللغة الإنجليزية، قم بترجمته إلى العربية باحترافية.
    2. أعد صياغة النص ولخصه ليكون مقالاً إخبارياً حصرياً وجذاباً.
    3. اكتب عنواناً جذاباً باللغة العربية.
    4. افصل بين العنوان والمقال برمز القوسين [العنوان] و [المقال] ليسهل برمجياً فصلهما.

    النص الأصلي:
    العنوان: {title}
    المحتوى: {content}
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text
        
        # استخراج العنوان والمقال من رد الذكاء الاصطناعي
        if "[المقال]" in text and "[العنوان]" in text:
            new_title = text.split("[المقال]")[0].replace("[العنوان]", "").strip()
            new_article = text.split("[المقال]")[1].strip()
            # تحويل النص إلى تنسيق HTML لبلوجر (استبدال الأسطر الجديدة بـ <br>)
            new_article_html = new_article.replace("\n", "<br>")
            return new_title, new_article_html
        else:
            print("لم يتمكن الذكاء الاصطناعي من تنسيق الرد بشكل صحيح.")
            return None, None
            
    except Exception as e:
        print(f"حدث خطأ أثناء الاتصال بالذكاء الاصطناعي: {e}")
        return None, None

# ==========================================
# 4. دالة النشر على بلوجر
# ==========================================

def post_to_blogger(title, content, label):
    """دالة لإرسال المقال الجاهز إلى مدونة بلوجر."""
    post_data = {
        'title': title,
        'content': content,
        'labels': [label]
    }
    
    try:
        request = blogger_service.posts().insert(blogId=BLOG_ID, body=post_data, isDraft=False)
        response = request.execute()
        print(f"تم النشر بنجاح! رابط المقال: {response.get('url')}")
    except Exception as e:
        print(f"حدث خطأ أثناء النشر على بلوجر: {e}")

# ==========================================
# 5. تشغيل البرنامج (السكربت الرئيسي)
# ==========================================

def main():
    print("بدأ جلب الأخبار التقنية...")
    posted_urls = get_posted_urls()
    
    for feed in FEEDS:
        print(f"\nجاري فحص المصدر: {feed['url']}")
        parsed_feed = feedparser.parse(feed['url'])
        
        # نأخذ أول 3 أخبار من كل مصدر لتجنب الضغط الزائد
        for entry in parsed_feed.entries[:3]:
            article_url = entry.link
            
            # التحقق مما إذا كان الخبر جديداً
            if article_url in posted_urls:
                print(f"الخبر منشور مسبقاً، سيتم تخطيه: {article_url}")
                continue
                
            print(f"عُثر على خبر جديد: {entry.title}")
            
            # محاولة سحب المحتوى الوصفي للخبر
            # بعض الخلاصات تستخدم summary وبعضها description
            content = entry.get('description', entry.get('summary', ''))
            
            # معالجة النص باستخدام الذكاء الاصطناعي
            print("جاري الترجمة وإعادة الصياغة...")
            new_title, new_html_content = process_content_with_ai(entry.title, content)
            
            if new_title and new_html_content:
                # نشر المقال
                print("جاري النشر على بلوجر...")
                post_to_blogger(new_title, new_html_content, feed['label'])
                
                # حفظ الرابط لعدم تكراره مستقبلاً
                save_posted_url(article_url)
                
                # تأخير زمني بسيط لتجنب حظر الواجهة البرمجية المجانية للذكاء الاصطناعي
                time.sleep(15) 
            else:
                print("تم تخطي الخبر بسبب فشل المعالجة.")

if __name__ == '__main__':
    main()

