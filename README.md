# 🍽️ MenuWise (메뉴와이즈)

**AI 기반 계층적 리뷰 요약 및 맞춤형 식당 추천 서비스**

## 👥 Team & Roles

| 역할       | 성명       | 담당 업무                                   |
| :--------- | :--------- | :------------------------------------------ |
| **Role 1** | **이성준** | 리뷰 크롤링 & DB 설계 (위치 기반 검색 포함) |
| **Role 2** | **김유미** | 프론트엔드 개발 (Flet UI, 상세 요약 노출)   |
| **Role 3** | **유다연** | 백엔드 API 개발 (FastAPI 서버, 피드백 로직) |
| **Role 4** | **박진우** | AI 모델 연동 (LLM 계층 요약, VLM 사진 매칭) |
| **Role 5** | **이경원** | PM & 아키텍처 (프로젝트 총괄 및 통합)       |

## 🌿 Branch Strategy

- **main**: 최종 발표용
- **develop**: 공용 작업장 (이 브랜치에서 작업하세요!)
- **feat/역할번호-기능명**: 각 팀원 개별 작업 공간

## 🔔 Running in local development

1. UV(Python 패키지 관리자) 설치: [가이드](https://docs.astral.sh/uv/getting-started/installation/)
2. UV 프로젝트 초기화
  ```shell
  uv sync
  ```
3. FastAPI 서버 실행
  ```shell
  uv run fastapi dev
  ```

## 사용 모델 및 라이선스

| 모델 | 라이선스 | 비고 |
|------|----------|------|
| [snunlp/KR-SBERT-V40K-klueNLI-augSTS](https://huggingface.co/snunlp/KR-SBERT-V40K-klueNLI-augSTS) | 미명시 | Citation 표기 |
| [google/siglip-base-patch16-256-multilingual](https://huggingface.co/google/siglip-base-patch16-256-multilingual) | Apache 2.0 | - |
| GPT-4o-mini (OpenAI API) | Proprietary | OpenAI ToS 준수 |

### Citation (KR-SBERT)

@misc{kr-sbert,
  author    = {Park, Suzi and Hyopil Shin},
  title     = {KR-SBERT: A Pre-trained Korean-specific Sentence-BERT model},
  year      = {2021},
  publisher = {GitHub},
  journal   = {GitHub repository},
  howpublished = {\url{https://github.com/snunlp/KR-SBERT}}
}