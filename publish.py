# -*- coding: utf-8 -*-
"""
깃허브 서버가 매일 실행하는 발행 스크립트.

하로님 컴퓨터가 아니라 '깃허브 서버'에서 돕니다.
그래서 컴퓨터가 꺼져 있어도 릴스가 올라갑니다.

하는 일:
  1. queue.json 에서 아직 안 올린 것 중 첫 번째를 고른다
  2. 이 저장소에 있는 영상의 인터넷 주소를 만든다 (jsDelivr)
  3. 인스타에 릴스로 올린다
  4. 첫 댓글을 단다
  5. queue.json 에 '올림' 표시를 하고 저장한다 (워크플로가 커밋)

이 파일은 사람이 직접 실행하지 않습니다.
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

토큰 = os.environ["IG_TOKEN"]
계정ID = os.environ["IG_USER_ID"]
사용자 = os.environ["GH_USER"]
저장소 = os.environ["GH_REPO"]

본진 = "https://graph.instagram.com"
한국시간 = timezone(timedelta(hours=9))
목록파일 = Path("queue.json")


def 오류설명(응답):
    try:
        오류 = 응답.json().get("error", {})
        return f"{오류.get('message', 응답.text[:200])} (코드 {오류.get('code', '?')})"
    except Exception:
        return f"HTTP {응답.status_code}: {응답.text[:200]}"


def 캡션제목(캡션: str) -> str:
    """캡션 첫 줄의 [제목] 을 꺼낸다. 하로님이 직접 올린 게시물이 어느 카드인지 알아보기 위해."""
    첫줄 = (캡션 or "").strip().split("\n")[0].strip()
    m = re.match(r"^\[(.+?)\]$", 첫줄)
    return m.group(1).strip() if m else ""


def 인스타_오늘게시물(오늘: str):
    """인스타 계정에 '오늘(한국시간)' 올라간 게시물을 가져온다.
    자동이 올린 것이든 하로님이 폰으로 직접 올린 것이든 다 잡힌다."""
    r = requests.get(
        f"{본진}/{계정ID}/media",
        params={"fields": "id,caption,timestamp", "limit": 10, "access_token": 토큰},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"[알림] 최근 게시물을 못 읽었습니다({오류설명(r)}). 발행 기록만으로 판단합니다.")
        return []
    결과 = []
    for m in r.json().get("data", []):
        ts = m.get("timestamp")            # 예: 2026-09-11T15:01:57+0000
        if not ts:
            continue
        t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z").astimezone(한국시간)
        if t.strftime("%Y-%m-%d") == 오늘:
            결과.append(m)
    return 결과


def 실행():
    목록 = json.loads(목록파일.read_text(encoding="utf-8"))
    오늘 = datetime.now(한국시간).strftime("%Y-%m-%d")

    # ── 하루에 한 장만 ────────────────────────────────────────
    # 인스타에 오늘 게시물이 이미 있으면 건너뛴다.
    # 하로님이 음악을 넣어 폰으로 직접 올린 날도 여기서 잡혀서, 자동이 알아서 비켜준다.
    오늘게시물 = 인스타_오늘게시물(오늘)
    if 오늘게시물:
        바뀜 = False
        for m in 오늘게시물:
            제목 = 캡션제목(m.get("caption", ""))
            for it in 목록["items"]:
                if it.get("status") == "pending" and 제목 and it["title"] == 제목:
                    it["status"] = "published"
                    it["published_at"] = datetime.now(한국시간).strftime("%Y-%m-%d %H:%M")
                    it["media_id"] = m["id"]
                    it["note"] = "직접 올림"
                    바뀜 = True
                    print(f"발행 목록의 「{제목}」을 직접 올리셨네요. '올림'으로 표시합니다.")
        if 바뀜:
            목록파일.write_text(json.dumps(목록, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"오늘({오늘})은 이미 {len(오늘게시물)}장 올라가 있습니다. 자동 발행은 건너뜁니다.")
        return 0

    # 인스타를 못 읽었을 때를 대비한 두 번째 잠금 (발행 기록 기준)
    if any((x.get("published_at") or "").startswith(오늘) for x in 목록["items"]):
        print(f"오늘({오늘})은 이미 한 장 올렸습니다. 내일 다시 올립니다.")
        return 0

    대기 = [x for x in 목록["items"] if x.get("status") == "pending"]

    if not 대기:
        print("올릴 카드가 다 떨어졌습니다. queue.json 에 새 항목을 추가하세요.")
        return 0

    항목 = 대기[0]

    # '@main' 대신 커밋 번호로 부른다.
    # @main 은 배달 서버(jsDelivr)가 옛 파일을 최대 12시간 캐시해 두고 계속 내주는 바람에,
    # 새 영상을 올려도 옛 영상이 발행됐다(2026-09-11, 9:16 옛 영상이 올라감).
    # 커밋 번호는 올릴 때마다 달라지므로 캐시가 끼어들 수 없다.
    커밋 = os.environ.get("GITHUB_SHA") or "main"
    영상주소 = f"https://cdn.jsdelivr.net/gh/{사용자}/{저장소}@{커밋}/videos/{항목['video']}"
    원본주소 = f"https://raw.githubusercontent.com/{사용자}/{저장소}/{커밋}/videos/{항목['video']}"

    print(f"오늘 올릴 카드: {항목['title']}")
    print(f"남은 카드: {len(대기)}장")
    print(f"영상 주소: {영상주소}")

    # 1) 배달 주소가 '영상'으로 제대로 인식되는지
    확인 = requests.get(영상주소, timeout=60, stream=True)
    종류 = 확인.headers.get("Content-Type", "")
    배달크기 = int(확인.headers.get("Content-Length") or 0)
    확인.close()
    if 확인.status_code != 200 or "video" not in 종류:
        print(f"[실패] 영상 주소를 인스타가 못 읽습니다. HTTP {확인.status_code}, {종류}")
        return 1

    # 2) 배달된 파일이 저장소 원본과 같은 파일인지 (크기 대조) — 캐시 사고 재발 방지
    원본 = requests.get(원본주소, timeout=60, stream=True)
    원본크기 = int(원본.headers.get("Content-Length") or 0)
    원본.close()
    if 원본크기 and 배달크기 != 원본크기:
        print(f"[실패] 배달 주소가 옛 영상을 주고 있습니다. 배달 {배달크기:,} vs 원본 {원본크기:,} bytes")
        return 1
    print(f"주소 확인 완료 ({종류}, {배달크기:,} bytes, 원본과 일치)")

    # 1. 자리 만들기
    응답 = requests.post(
        f"{본진}/{계정ID}/media",
        data={
            "media_type": "REELS",
            "video_url": 영상주소,
            "caption": 항목["caption"],
            "share_to_feed": "true",
            "access_token": 토큰,
        },
        timeout=120,
    )
    if 응답.status_code != 200:
        print(f"[실패] 자리를 못 만들었습니다: {오류설명(응답)}")
        return 1
    자리ID = 응답.json()["id"]
    print(f"자리 번호 {자리ID}")

    # 2. 인스타가 영상 처리를 끝낼 때까지 기다리기
    시작 = time.time()
    while time.time() - 시작 < 600:
        상태응답 = requests.get(
            f"{본진}/{자리ID}",
            params={"fields": "status_code,status", "access_token": 토큰},
            timeout=30,
        )
        상태 = 상태응답.json().get("status_code", "")
        if 상태 == "FINISHED":
            print("영상 처리 완료")
            break
        if 상태 == "ERROR":
            print(f"[실패] 인스타가 영상을 거부했습니다: {상태응답.json()}")
            return 1
        print(f"  처리 중... ({int(time.time()-시작)}초)")
        time.sleep(10)
    else:
        print("[실패] 10분을 기다렸는데 처리가 안 끝났습니다.")
        return 1

    # 3. 발행
    응답 = requests.post(
        f"{본진}/{계정ID}/media_publish",
        data={"creation_id": 자리ID, "access_token": 토큰},
        timeout=60,
    )
    if 응답.status_code != 200:
        print(f"[실패] 발행하지 못했습니다: {오류설명(응답)}")
        return 1
    게시물ID = 응답.json()["id"]
    print(f"발행 완료! 게시물 번호 {게시물ID}")

    # 4. 첫 댓글 (실패해도 게시는 이미 끝났으므로 넘어간다)
    첫댓글 = 항목.get("first_comment") or 목록.get("default_first_comment", "")
    if 첫댓글:
        댓글응답 = requests.post(
            f"{본진}/{게시물ID}/comments",
            data={"message": 첫댓글, "access_token": 토큰},
            timeout=60,
        )
        if 댓글응답.status_code == 200:
            print("첫 댓글 완료")
        else:
            print(f"[알림] 첫 댓글 실패(게시물은 정상): {오류설명(댓글응답)}")

    # 5. 올림 표시
    항목["status"] = "published"
    항목["published_at"] = datetime.now(한국시간).strftime("%Y-%m-%d %H:%M")
    항목["media_id"] = 게시물ID
    목록파일.write_text(
        json.dumps(목록, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    남은수 = len([x for x in 목록["items"] if x.get("status") == "pending"])
    print(f"남은 카드: {남은수}장" + ("   <- 슬슬 채워주세요!" if 남은수 <= 5 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(실행())
