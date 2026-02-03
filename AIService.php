<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class AIService
{
    protected string $apiKey;
    protected string $model;
    protected float $temperature;
    protected int $maxTokens;

    public function __construct()
    {
        $this->apiKey = config('services.openai.api_key');
        $this->model = 'gpt-3.5-turbo'; // используем только рабочую модель
        $this->temperature = 0.7;
        $this->maxTokens = 1200;
    }

    /**
     * Получить ответ от OpenAI
     */
    public function getAnswer(string $message, ?string $systemMessage = null): string
    {
        $messages = [];

        if ($systemMessage) {
            $messages[] = [
                'role' => 'system',
                'content' => $systemMessage
            ];
        }

        $messages[] = [
            'role' => 'user',
            'content' => $message
        ];

        try {
            $response = Http::withHeaders([
                'Authorization' => "Bearer {$this->apiKey}",
                'Content-Type'  => 'application/json',
            ])->timeout(30)
                ->post('https://api.openai.com/v1/chat/completions', [
                    'model' => $this->model,
                    'messages' => $messages,
                    'temperature' => $this->temperature,
                    'max_tokens' => $this->maxTokens,
                ]);

            if ($response->failed()) {
                Log::warning('OpenAI API failed', ['status' => $response->status(), 'body' => $response->body()]);
                throw new \RuntimeException('OpenAI API request failed');
            }

            $data = $response->json();
        } catch (\Throwable $e) {
            Log::warning('OpenAI API error: '.$e->getMessage());
            throw $e;
        }

        Log::info('OpenAI response: '.json_encode($data));

        if (isset($data['choices'][0]['message']['content'])) {
            return trim($data['choices'][0]['message']['content']);
        }

        throw new \RuntimeException('Empty response from OpenAI');
    }

    /**
     * Универсальный метод для ведения диалога с сохранением контекста
     * @param array<int, array{role:string,content:string}> $messages
     */
    public function chatWithContext(array $messages): string
    {
        try {
            $response = Http::withHeaders([
                'Authorization' => "Bearer {$this->apiKey}",
                'Content-Type'  => 'application/json',
            ])->timeout(30)
                ->post('https://api.openai.com/v1/chat/completions', [
                    'model' => $this->model,
                    'messages' => $messages,
                    'temperature' => $this->temperature,
                    'max_tokens' => $this->maxTokens,
                ]);

            $data = $response->json();

            Log::info('OpenAI response: '.json_encode($data));

            if (isset($data['choices'][0]['message']['content'])) {
                return trim($data['choices'][0]['message']['content']);
            }

            return 'Сейчас мне сложно поддержать диалог, попробуй чуть позже.';
        } catch (\Exception $e) {
            Log::warning("OpenAI API error: ".$e->getMessage());
            return 'Сейчас мне сложно поддержать диалог, попробуй чуть позже.';
        }
    }
}
