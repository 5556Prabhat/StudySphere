from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from hub.models import (
    DiscussionMessage,
    GroupMembership,
    MaterialReview,
    StudyGroup,
    StudyMaterial,
)


class Command(BaseCommand):
    help = "Seed demo users, study materials, reviews, and study groups for local acceptance review."

    def handle(self, *args, **options):
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@studysphere.example", "is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password("AdminPass123!")
            admin.save()

        alice, created = User.objects.get_or_create(
            username="alice",
            defaults={"email": "alice@studysphere.example"},
        )
        if created:
            alice.set_password("StudyPass123!")
            alice.save()
        alice.profile.institution = "National Institute of Technology"
        alice.profile.course = "Computer Science"
        alice.profile.study_goal = "Master algorithms and distributed systems"
        alice.profile.save()

        rohan, created = User.objects.get_or_create(
            username="rohan",
            defaults={"email": "rohan@studysphere.example"},
        )
        if created:
            rohan.set_password("StudyPass123!")
            rohan.save()
        rohan.profile.institution = "Indian Institute of Science"
        rohan.profile.course = "Applied Mathematics"
        rohan.profile.study_goal = "Prepare for linear algebra & calculus finals"
        rohan.profile.save()

        m1, _ = StudyMaterial.objects.get_or_create(
            title="Graph Algorithms Study Guide",
            owner=alice,
            defaults={
                "description": "Comprehensive notes covering BFS, DFS, Dijkstra, Bellman-Ford, and Minimum Spanning Trees with complexity analysis.",
                "subject": "Computer Science",
                "topic": "Graph Theory & Algorithms",
                "material_type": StudyMaterial.MaterialType.NOTE,
                "external_link": "https://cp-algorithms.com/graph/breadth-first-search.html",
                "extracted_text": (
                    "Breadth-first search (BFS) explores vertices in layers of increasing distance from the source vertex. "
                    "Depth-first search (DFS) explores as far as possible along each branch before backtracking. "
                    "Dijkstra's algorithm finds shortest paths from a source vertex in graphs with non-negative edge weights. "
                    "Kruskal's and Prim's greedy algorithms compute a minimum spanning tree in O(E log V) time."
                ),
            },
        )

        m2, _ = StudyMaterial.objects.get_or_create(
            title="Multivariable Calculus Practice Set",
            owner=rohan,
            defaults={
                "description": "Worked examples and practice questions on partial derivatives, gradients, directional derivatives, and multiple integrals.",
                "subject": "Mathematics",
                "topic": "Multivariable Calculus",
                "material_type": StudyMaterial.MaterialType.QUESTION_PAPER,
                "external_link": "https://ocw.mit.edu/courses/18-02sc-multivariable-calculus-fall-2010/",
                "extracted_text": (
                    "The gradient vector points in the direction of steepest ascent of a scalar field. "
                    "A partial derivative measures how a multivariable function changes as one variable varies while others are held constant. "
                    "Green's theorem relates a line integral around a simple closed curve to a double integral over the plane region it bounds."
                ),
            },
        )

        MaterialReview.objects.update_or_create(
            material=m1,
            author=rohan,
            defaults={"rating": 5, "comment": "Clear complexity breakdown and great summary of shortest-path trade-offs."},
        )

        group, _ = StudyGroup.objects.get_or_create(
            name="Algorithms & Data Structures Circle",
            owner=alice,
            defaults={
                "subject": "Computer Science",
                "description": "Weekly problem-solving group for graph algorithms, dynamic programming, and complexity proofs.",
            },
        )
        GroupMembership.objects.get_or_create(group=group, user=alice)
        GroupMembership.objects.get_or_create(group=group, user=rohan)
        if not group.messages.exists():
            DiscussionMessage.objects.create(
                group=group,
                author=alice,
                body="Welcome everyone! Let's start with shortest-path algorithms this week.",
            )

        from hub.services import get_or_create_global_group
        global_gc = get_or_create_global_group(alice)
        GroupMembership.objects.get_or_create(group=global_gc, user=rohan)
        GroupMembership.objects.get_or_create(group=global_gc, user=admin)
        if global_gc.messages.count() <= 1:
            DiscussionMessage.objects.create(
                group=global_gc,
                author=rohan,
                body="Hey everyone! Quick doubt: when should we use Bellman-Ford instead of Dijkstra?",
            )
            DiscussionMessage.objects.create(
                group=global_gc,
                author=alice,
                body="Use Bellman-Ford whenever the graph has negative weight edges! Dijkstra assumes non-negative edge weights.",
            )

        self.stdout.write(self.style.SUCCESS("Seeded demo accounts (admin, alice, rohan), materials, Global GC, and leaderboard data."))
