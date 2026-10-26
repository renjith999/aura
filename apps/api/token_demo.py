
import tiktoken

encoding = tiktoken.get_encoding("o200k_base")

messages = [
    {"role": "user", "content": "I bought a new laptop."},
    {"role": "assistant", "content": "Which laptop did you buy?"},
    {"role": "user", "content": "A Lenovo LOQ."},
]

total_tokens = 0

for message in messages:
    count = len(encoding.encode(message["content"]))
    total_tokens += count

    print(f"{message['role']}: {message['content']}")
    print(f"  Tokens: {count}")

print(f"\nTotal message-content tokens: {total_tokens}")
