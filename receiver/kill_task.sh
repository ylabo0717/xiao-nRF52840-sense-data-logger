#!/bin/bash

PIDS=$(lsof -ti :8050)

if [ -z "$PIDS" ]; then
  echo "ポート8050を使用しているプロセスは見つかりませんでした。"
else
  echo "ポート8050を使用しているプロセスを終了します: $PIDS"
  kill -9 $PIDS
fi

