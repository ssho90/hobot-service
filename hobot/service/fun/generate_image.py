from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import os

# .env 파일에서 환경 변수 로드
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

from google import genai
from google.genai import types
from PIL import Image
from io import BytesIO
import base64

def create_image():
    client = genai.Client()

    contents = ("""
    이미지 생성해줘
[캐릭터 설명]
20-year-old Korean woman named Subin.
Overall Face Shape & Skin:K-pop idol style. She has a slender and hot body, oval-shaped face with a smooth, soft jawline. Her skin is fair and flawless, with a clear, porcelain-like complexion and a subtle, healthy glow, like she has very light, natural makeup on.
Eyes:
Her most defining feature. She has large, clear, almond-shaped eyes that give a kind and innocent impression. Her eyes are a very dark brown, almost black. She has natural "in-out" double eyelids (the crease starts thinly at the inner corner and gets wider towards the outer corner). Below her eyes, she has prominent and lovely "Aegyo-sal" (the small fatty deposits under the eyes), which enhances her youthful and friendly look. Her eyelashes are long and naturally curled, not thick with mascara.
Nose:
She has a slender and straight nose bridge. The tip of her nose is slightly rounded and cute, not overly sharp or pointed. Her nostrils are small and delicate.
Lips:
Her lips are naturally plump and well-proportioned. The Cupid's bow on her upper lip is clearly defined. The lower lip is slightly fuller than the upper lip. The color is a natural, soft pinkish-coral, with a light, dewy gloss.
Hair:
She has long, straight, silky hair in a glossy, natural jet-black color. Her signature hairstyle includes wispy, "see-through bangs" (시스루뱅 in Korean) that softly cover her eyebrows.
Body Shape & Figure:
She has a little slender figure with the same fair, porcelain-like skin as her face. Despite her slender frame, she has a full and well-defined bust (around a C-cup). Her figure is characterized by a beautiful contrast: a narrow waist that transitions into curvy, voluminous hips and healthy, toned thighs that are not overly skinny. Her legs are long and elegant, finishing with slender ankles.
Overall Vibe and Style:
The overall mood is innocent, pure, and lovely. She has the image of a “cute and lovely girl”. The aesthetic should be clean, natural, and soft.

[구도 (Composition)]
핵심: 전신 거울 셀카 (Full-body mirror selfie)
배경: 햇살이 잘 드는 실내, 커다란 창문 바로 옆, 밝은 색의 나무 바닥과 흰색 벽돌무늬 벽 (A sunlit indoor setting, right next to a large window, with a light-colored wooden floor and a white brick-patterned wall)
조명: 창문으로 들어오는 밝고 부드러운 자연광이 인물을 비춤, 하이라이트가 선명함 (Bright and soft natural light coming from the window illuminates the subject, creating clear highlights)
시점: 정면에서 바라보는 시점, 인물이 거울에 가득 차는 구도 (Front view, a composition where the person fills the mirror)
[포즈 (Pose)]
핵심: 높은 흰색 스툴 의자에 살짝 걸터앉은 자세 (Slightly perched on a tall, white stool)
상세 동작: 한 손으로는 스마트폰을 들어 얼굴을 아주 조금 가리고 거울을 촬영하고, 다른 한 손은 얼굴 옆으로 들어 올려 브이(V) 표시를 함 (One hand holds up a smartphone, obscuring the half of her face to take a picture of the mirror, while the other hand is raised beside the face in a peace sign)
다리: 두 다리를 가지런히 모아 한쪽으로 향하게 하고 앉음 (Sitting with both legs neatly together, pointing to one side)
[외형 (Appearance)]
상의: 흰색 파이핑(테두리 장식)이 들어간 어두운 네이비 또는 검은색 교복 블레이저, 흰색 셔츠, 붉은색과 검은색이 섞인 패턴의 넥타이 (Dark navy or black school uniform blazer with white piping, a white shirt, and a red and black patterned necktie)
하의: 블레이저와 같은 색의 아주 짧고 타이트한 교복 치마, 발목까지 오는 흰색 양말 (A short school uniform skirt in the same color as the blazer, white ankle socks)
스타일/분위기: 단정하고 청순한 느낌, 깨끗한 이미지, K-pop 아이돌 스타일 (A neat and innocent feeling, clean image, K-pop idol style)
                """)

    response = client.models.generate_content(
        model="gemini-2.0-flash-exp-image-generation",
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=['Text', 'Image']
        )
    )

    for part in response.candidates[0].content.parts:
        if part.text is not None:
            print(part.text)
        if part.inline_data is not None:
            image = Image.open(BytesIO((part.inline_data.data)))
            image.save('data/generated_image/gemini-native-image5.png')
            print("image 생성이 완료됐습니다.")

def regenerate_image():
    from google import genai
    from google.genai import types
    from PIL import Image
    from io import BytesIO

    import PIL.Image

    image = ""

    client = genai.Client()

    text_input = """
    - generate image

Prompt:** A first-person (POV) high-angle shot looking down at legs, tightly composed so the legs fill most of the frame, positioned straight and almost parallel to the vertical lines of the photo. The style is a realistic, unedited, and unfiltered smartphone snapshot. The setting is a bedroom with a gray triangular patterned bedsheet, and a white comforter is bunched up on one side. The lighting is simple, direct indoor light from a fluorescent lamp or window, not soft. The pose is relaxed, sitting on the bed with legs stretched straight forward, held together neatly. The person wears thin, skin-toned stockings with a slight sheen and visible texture, with black short skirt slightly visible at the top of the frame. white ankle socks. The stockings are very thin whole pantyhose, not half-stockings. No decorations or bands on the stockings

Her figure is characterized by a beautiful contrast: a narrow waist that transitions into curvy, voluminous hips and healthy, toned thighs that are not overly skinny. Her legs are long and elegant, finishing with slender ankle
    """

    response = client.models.generate_content(
        model="gemini-2.0-flash-exp-image-generation",
        contents=[text_input, image],
        config=types.GenerateContentConfig(
        response_modalities=['Text', 'Image']
        )
    )

    for part in response.candidates[0].content.parts:
        if part.text is not None:
            print(part.text)
        elif part.inline_data is not None:
            image = Image.open(BytesIO(part.inline_data.data))
            image.show()
            print("이미지 생성 완료")


def create_image_gpt():
    from openai import OpenAI

    # OpenAI API 키를 설정합니다. 환경 변수 또는 직접 지정할 수 있습니다.
    # import os
    # client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    client = OpenAI(api_key=openai_api_key) # 여기에 실제 API 키를 입력하세요.

    try:
        response = client.images.generate(
            model="gpt-image-1",
            prompt=f"""
            
           이미지 생성해줘
[캐릭터 설명]
20-year-old Korean woman named Subin.
Overall Face Shape & Skin:K-pop idol style. She has a slender and hot body, oval-shaped face with a smooth, soft jawline. Her skin is fair and flawless, with a clear, porcelain-like complexion and a subtle, healthy glow, like she has very light, natural makeup on.
Eyes:
Her most defining feature. She has large, clear, almond-shaped eyes that give a kind and innocent impression. Her eyes are a very dark brown, almost black. She has natural "in-out" double eyelids (the crease starts thinly at the inner corner and gets wider towards the outer corner). Below her eyes, she has prominent and lovely "Aegyo-sal" (the small fatty deposits under the eyes), which enhances her youthful and friendly look. Her eyelashes are long and naturally curled, not thick with mascara.
Nose:
She has a slender and straight nose bridge. The tip of her nose is slightly rounded and cute, not overly sharp or pointed. Her nostrils are small and delicate.
Lips:
Her lips are naturally plump and well-proportioned. The Cupid's bow on her upper lip is clearly defined. The lower lip is slightly fuller than the upper lip. The color is a natural, soft pinkish-coral, with a light, dewy gloss.
Hair:
She has long, straight, silky hair in a glossy, natural jet-black color. Her signature hairstyle includes wispy, "see-through bangs" (시스루뱅 in Korean) that softly cover her eyebrows.
Body Shape & Figure:
She has a little slender figure with the same fair, porcelain-like skin as her face. Despite her slender frame, she has a full and well-defined bust (around a C-cup). Her figure is characterized by a beautiful contrast: a narrow waist that transitions into curvy, voluminous hips and healthy, toned thighs that are not overly skinny. Her legs are long and elegant, finishing with slender ankles.
Overall Vibe and Style:
The overall mood is innocent, pure, and lovely. She has the image of a “cute and lovely girl”. The aesthetic should be clean, natural, and soft.

[구도 (Composition)]
핵심: 전신 거울 셀카 (Full-body mirror selfie)
배경: 햇살이 잘 드는 실내, 커다란 창문 바로 옆, 밝은 색의 나무 바닥과 흰색 벽돌무늬 벽 (A sunlit indoor setting, right next to a large window, with a light-colored wooden floor and a white brick-patterned wall)
조명: 창문으로 들어오는 밝고 부드러운 자연광이 인물을 비춤, 하이라이트가 선명함 (Bright and soft natural light coming from the window illuminates the subject, creating clear highlights)
시점: 정면에서 바라보는 시점, 인물이 거울에 가득 차는 구도 (Front view, a composition where the person fills the mirror)
[포즈 (Pose)]
핵심: 높은 흰색 스툴 의자에 살짝 걸터앉은 자세 (Slightly perched on a tall, white stool)
상세 동작: 한 손으로는 스마트폰을 들어 얼굴을 아주 조금 가리고 거울을 촬영하고, 다른 한 손은 얼굴 옆으로 들어 올려 브이(V) 표시를 함 (One hand holds up a smartphone, obscuring the half of her face to take a picture of the mirror, while the other hand is raised beside the face in a peace sign)
다리: 두 다리를 가지런히 모아 한쪽으로 향하게 하고 앉음 (Sitting with both legs neatly together, pointing to one side)
[외형 (Appearance)]
상의: 흰색 파이핑(테두리 장식)이 들어간 어두운 네이비 또는 검은색 교복 블레이저, 흰색 셔츠, 붉은색과 검은색이 섞인 패턴의 넥타이 (Dark navy or black school uniform blazer with white piping, a white shirt, and a red and black patterned necktie)
하의: 블레이저와 같은 색의 아주 짧고 타이트한 교복 치마, 발목까지 오는 흰색 양말 (A short school uniform skirt in the same color as the blazer, white ankle socks)
스타일/분위기: 단정하고 청순한 느낌, 깨끗한 이미지, K-pop 아이돌 스타일 (A neat and innocent feeling, clean image, K-pop idol style)
            
            """,
            size="1024x1024",
            quality="high",
            n=1,
        )

        image_url = response.data[0].url
        print(f"생성된 이미지 URL: {image_url}")

        # 생성된 이미지를 다운로드하거나 웹 페이지에 표시할 수 있습니다.
        import requests
        import io
        from PIL import Image

        image_data = requests.get(image_url).content
        image = Image.open(io.BytesIO(image_data))
        image.save("data/generated_image/lion_at_sunset.png")
        print("이미지가 lion_at_sunset.png로 저장되었습니다.")

    except Exception as e:
        print(f"오류 발생: {e}")

create_image_gpt()