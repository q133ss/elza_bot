<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class TgService
{
    protected string $token;

    public function __construct()
    {
        $this->token = config('services.telegram.bot_token');
    }

    /**
     * Общая отправка текста (без клавиатуры или с reply keyboard)
     *
     * $keyboard — массив массивов строк [['A','B'], ['C']]
     */
    public function sendMessage(int $chatId, string $text, array $keyboard = null)
    {
        $data = [
            'chat_id' => $chatId,
            'text' => $text,
            'parse_mode' => 'HTML',
            'disable_web_page_preview' => true,
        ];

        if ($keyboard) {
            $data['reply_markup'] = json_encode([
                'keyboard' => $keyboard,
                'resize_keyboard' => true,
                'one_time_keyboard' => true
            ]);
        }

        $this->post('sendMessage', $data);
    }

    /**
     * Inline-клавиатура
     * $buttons — массив строк или массив массивов [['text'=>'1','callback_data'=>'cb1'], ...]
     * Простой вариант: $inline = [['Подписка','subscribe_cb'], ['Назад','back_cb']]
     */
    public function sendInlineKeyboard(int $chatId, string $text, array $buttons): void
    {
        // buttons expected as 2D array of ['text'=>..,'callback_data'=>..] rows
        $inline = ['inline_keyboard' => $buttons];

        $this->post('sendMessage', [
            'chat_id' => $chatId,
            'text' => $text,
            'parse_mode' => 'HTML',
            'reply_markup' => json_encode($inline),
        ]);
    }

    protected function post(string $method, array $data)
    {
        try {
            Http::post("https://api.telegram.org/bot{$this->token}/{$method}", $data);
        } catch (\Throwable $e) {
            Log::error("Telegram API error: ".$e->getMessage(), $data);
        }
    }
}
