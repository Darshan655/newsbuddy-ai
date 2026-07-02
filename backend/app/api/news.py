from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date

from app.models.database import get_db, NewsItem
from app.models.schemas import NewsCreate, NewsUpdate, NewsResponse

router = APIRouter()


@router.post("/", response_model=NewsResponse, status_code=201)
def create_news(news_in: NewsCreate, db: Session = Depends(get_db)):
    """Add a news item. Called by admin or scraper pipeline."""
    item = NewsItem(
        title=news_in.title,
        summary=news_in.summary,
        full_content=news_in.full_content,
        source_url=news_in.source_url,
        source_name=news_in.source_name,
        city=news_in.city.strip(),
        state=news_in.state,
        country=news_in.country,
        category=news_in.category,
        language=news_in.language,
        importance_score=news_in.importance_score,
        is_breaking=news_in.is_breaking,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/", response_model=List[NewsResponse])
def list_news(
    city: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    is_breaking: Optional[bool] = Query(None),
    news_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List news items with filters. Used to populate call scripts."""
    q = db.query(NewsItem).filter(NewsItem.is_active == True)

    if city:
        q = q.filter(NewsItem.city.ilike(f"%{city}%"))
    if category:
        q = q.filter(NewsItem.category == category)
    if language:
        q = q.filter(NewsItem.language == language)
    if is_breaking is not None:
        q = q.filter(NewsItem.is_breaking == is_breaking)
    if news_date:
        q = q.filter(NewsItem.news_date >= datetime.combine(news_date, datetime.min.time()))

    return (
        q.order_by(NewsItem.importance_score.desc(), NewsItem.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/for-user/{user_id}", response_model=List[NewsResponse])
def get_news_for_user(
    user_id: int,
    limit: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """
    Get top N news items personalised for a user.
    Filters by their city, language, and topic preferences.
    """
    from app.models.database import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    q = db.query(NewsItem).filter(
        NewsItem.is_active == True,
        NewsItem.city.ilike(f"%{user.city}%"),
        NewsItem.language == user.language,
    )

    if user.topics:
        from sqlalchemy import or_
        topic_filters = [NewsItem.category == topic for topic in user.topics]
        q = q.filter(or_(*topic_filters))

    items = (
        q.order_by(NewsItem.importance_score.desc(), NewsItem.created_at.desc())
        .limit(limit)
        .all()
    )

    # Fall back to any city news if not enough topic-specific items
    if len(items) < 3:
        fallback = (
            db.query(NewsItem)
            .filter(NewsItem.is_active == True, NewsItem.city.ilike(f"%{user.city}%"))
            .order_by(NewsItem.importance_score.desc())
            .limit(limit)
            .all()
        )
        seen_ids = {i.id for i in items}
        for item in fallback:
            if item.id not in seen_ids:
                items.append(item)
        items = items[:limit]

    return items


@router.get("/{news_id}", response_model=NewsResponse)
def get_news_item(news_id: int, db: Session = Depends(get_db)):
    item = db.query(NewsItem).filter(NewsItem.id == news_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="News item not found")
    return item


@router.put("/{news_id}", response_model=NewsResponse)
def update_news(news_id: int, news_in: NewsUpdate, db: Session = Depends(get_db)):
    item = db.query(NewsItem).filter(NewsItem.id == news_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="News item not found")

    update_data = news_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{news_id}", status_code=204)
def delete_news(news_id: int, db: Session = Depends(get_db)):
    item = db.query(NewsItem).filter(NewsItem.id == news_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="News item not found")
    item.is_active = False
    db.commit()
    return None
