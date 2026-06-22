from openai import OpenAI
from typing import List, Dict
from app.config import get_settings

settings = get_settings()


class DeepSeekClient:
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self.model = "deepseek-chat"

    def chat(self, messages: list, temperature: float = 0.7) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content

    def chat_with_system(self, system_prompt: str, user_message: str, temperature: float = 0.7) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return self.chat(messages, temperature)

    def chat_with_history(
        self, 
        system_prompt: str, 
        history: List[Dict[str, str]], 
        user_message: str,
        temperature: float = 0.7
    ) -> str:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return self.chat(messages, temperature)
