import json
import subprocess
from pathlib import Path
from datasets import Dataset
from unsloth import FastLanguageModel
from unsloth.chat_templates import get_chat_template, train_on_responses_only
from trl import SFTTrainer, SFTConfig

MODEL_NAME = "unsloth/Qwen2.5-3B-Instruct-bnb-4bit"
MAX_SEQ_LENGTH = 2048

def load_jsonl(path: str) -> Dataset:
    rows = [json.loads(line) for line in Path(path).open("r", encoding="utf-8") if line.strip()]
    return Dataset.from_list(rows)

def main():
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=32,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    tokenizer = get_chat_template(tokenizer, chat_template="qwen-2.5")
    raw_ds = load_jsonl("dataset/aegiscore_train.jsonl")

    def format_prompts(examples):
        texts = [
            tokenizer.apply_chat_template(convo, tokenize=False, add_generation_prompt=False)
            for convo in examples["messages"]
        ]
        return {"text": texts}

    train_ds = raw_ds.map(format_prompts, batched=True)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        args=SFTConfig(
            dataset_text_field="text",
            max_length=MAX_SEQ_LENGTH,
            per_device_train_batch_size=4,
            gradient_accumulation_steps=2,
            warmup_steps=15,
            num_train_epochs=2,
            learning_rate=2e-4,
            fp16=False,
            bf16=True,
            logging_steps=10,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="cosine",
            seed=42,
            output_dir="outputs/aegiscore_checkpoints",
            report_to="none",
        ),
    )

    # Mask system/user tokens so loss trains strictly on valid JSON assistant plans
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    )

    trainer.train()

    gguf_dir = Path("models/aegiscore-3b-gguf")
    model.save_pretrained("lora_adapters/aegiscore-3b")
    tokenizer.save_pretrained("lora_adapters/aegiscore-3b")
    model.save_pretrained_gguf(str(gguf_dir), tokenizer, quantization_method="q4_k_m")

    gguf_files = list(gguf_dir.glob("*.gguf"))
    if gguf_files:
        gguf_path = gguf_files[0].resolve()
        modelfile = Path("Modelfile")
        modelfile.write_text(
            f'FROM {gguf_path}\n'
            'TEMPLATE """{{- if .System }}<|im_start|>system\n{{ .System }}<|im_end|>\n{{- end }}'
            '{{- range .Messages }}<|im_start|>{{ .Role }}\n{{ .Content }}<|im_end|>\n{{- end }}'
            '<|im_start|>assistant\n"""\n'
            'PARAMETER stop "<|im_start|>"\n'
            'PARAMETER stop "<|im_end|>"\n'
            'PARAMETER temperature 0\n'
            'PARAMETER num_ctx 4096\n',
            encoding="utf-8",
        )
        subprocess.run(["ollama", "create", "aegiscore", "-f", "Modelfile"], check=True)
        print("Registered fine-tuned 'aegiscore' model in Ollama!")

if __name__ == "__main__":
    main()
